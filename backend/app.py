from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime
import io
import json
import os
from pathlib import Path
import uuid

from dotenv import load_dotenv
from fastapi import FastAPI,File,Form,HTTPException,UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image,UnidentifiedImageError
from pillow_heif import register_heif_opener
from pydantic import BaseModel,Field

from .store import Store,public_scan
from .service import ScanService
from .images import normalize_upload
from .luminal_transport import settings as cloud_settings

ROOT=Path(__file__).resolve().parents[1]
load_dotenv(ROOT/'.env',override=True)
register_heif_opener()


class EnrollmentSelection(BaseModel):
    object_id:str
    display_name:str=Field(min_length=1,max_length=100)


class EnrollmentRequest(BaseModel):
    baseline_scan_id:str
    objects:list[EnrollmentSelection]=Field(min_length=1,max_length=50)


class IdentityRequest(BaseModel):
    user_confirmed_name:str|None=Field(default=None,min_length=1,max_length=100)
    ignored:bool|None=None


class IdentityLinkRequest(BaseModel):
    member_id:str


def create_app(db_path=None,service_factory=ScanService):
    store=Store(db_path or ROOT/os.getenv('FIELDDELTA_DB','data/fielddelta.db'))
    executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='fielddelta-scans')
    service=service_factory(store)

    @asynccontextmanager
    async def lifespan(app):
        for scan_id in store.recover():
            executor.submit(service.process,scan_id)
        with store.connection() as db:
            pending=[row['scan_id'] for row in db.execute('SELECT scan_id FROM removal_reviews WHERE status="queued"')]
        for scan_id in pending:
            executor.submit(service.review_removal,scan_id)
        yield
        executor.shutdown(wait=True)

    app=FastAPI(title='FieldDelta Experimental Demo API',lifespan=lifespan)
    app.state.store=store

    def require_site(site_id,account_id=None):
        site=store.site(site_id)
        if site is None:
            raise HTTPException(404,'Unknown site')
        if account_id is not None and account_id!=site['account_id']:
            raise HTTPException(403,'Account does not own this site')
        return site

    @app.get('/health')
    def health():
        config=cloud_settings()
        return dict(status='ok',vision_status='experimental_not_production_ready',authentication='demo_only',
                    cloud_provider='luminal',cloud_model=config['model'],cloud_configured=bool(config['key']),cloud_enabled=config['enabled'])

    @app.get('/accounts')
    def accounts():
        return store.accounts()

    @app.get('/sites')
    def sites(account_id:str|None=None):
        return store.sites(account_id)

    @app.get('/sites/{site_id}/state')
    def state(site_id:str):
        site=require_site(site_id)
        latest=store.latest(site_id)
        return dict(site=site,has_baseline=latest is not None,
                    active_session=store.active_session(site_id),sessions=store.sessions(site_id),has_history=bool(store.scans(site_id)),
                    latest_scan=store.public_scan(latest) if latest else None,
                    objects=store.objects(latest['id']) if latest else [],
                    tracked_objects=store.memory(site_id),registry=store.registry(site_id),
                    interpretation='Observed candidates, not a guaranteed inventory; review required')

    @app.get('/sites/{site_id}/scans')
    def history(site_id:str):
        require_site(site_id)
        return [store.public_scan(s) for s in store.scans(site_id)]

    @app.get('/sites/{site_id}/sessions')
    def sessions(site_id:str):
        require_site(site_id)
        return store.sessions(site_id)

    @app.get('/scans/{scan_id}')
    def get_scan(scan_id:str):
        scan=store.scan(scan_id)
        if scan is None:
            raise HTTPException(404,'Unknown scan')
        return store.public_scan(scan)

    @app.get('/scans/{scan_id}/image')
    def get_image(scan_id:str):
        scan=store.scan(scan_id)
        if scan is None:
            raise HTTPException(404,'Unknown scan')
        return FileResponse(scan['image_path'],media_type='image/jpeg')

    @app.get('/scans/{scan_id}/detail')
    def scan_detail(scan_id:str):
        scan=store.scan(scan_id)
        if scan is None:
            raise HTTPException(404,'Unknown scan')
        return dict(**store.public_scan(scan),detected_objects=store.objects(scan_id),
                    product_objects=store.product_objects(scan),
                    observations=store.observations(scan_id),local_evidence=store.local_evidence(scan_id),
                    cloud_evidence=store.cloud_evidence(scan_id),
                    registry=store.registry(scan['site_id'],scan['session_id']),registry_scope='Enrollment for this inspection session')

    @app.post('/sites/{site_id}/scan',status_code=202)
    async def upload(site_id:str,account_id:str=Form(...),site_id_field:str=Form(...,alias='site_id'),
                     timestamp:str=Form(...),image:UploadFile=File(...),
                     new_inspection:bool=Form(False),session_id:str|None=Form(None),
                     image_orientation:int|None=Form(None,ge=1,le=8)):
        require_site(site_id,account_id)
        if site_id!=site_id_field:
            raise HTTPException(400,'Path and multipart site_id differ')
        try:
            parsed=datetime.fromisoformat(timestamp.replace('Z','+00:00'))
            if parsed.tzinfo is None:
                raise ValueError()
        except ValueError:
            raise HTTPException(422,'Timestamp must be ISO 8601 with timezone')
        data=bytearray()
        while chunk:=await image.read(1024*1024):
            data.extend(chunk)
            if len(data)>20*1024*1024:
                raise HTTPException(413,'Image exceeds 20MB')
        try:
            with Image.open(io.BytesIO(data)) as source:
                if source.width*source.height>30_000_000:
                    raise HTTPException(413,'Image exceeds 30 megapixels')
                photo,orientation_info=normalize_upload(source,image_orientation)
            photo.thumbnail((2048,2048))
        except (UnidentifiedImageError,OSError,ValueError,Image.DecompressionBombError):
            raise HTTPException(415,'Unreadable image; upload JPEG, PNG or HEIC')
        scan_id=str(uuid.uuid4())
        directory=ROOT/'uploads'/site_id
        directory.mkdir(parents=True,exist_ok=True)
        path=directory/f'{scan_id}.jpg'
        photo.save(path,quality=92)
        try:
            store.create_scan(scan_id,site_id,parsed.isoformat(),path,new_inspection,session_id)
        except ValueError as error:
            path.unlink(missing_ok=True)
            raise HTTPException(409,str(error))
        path.with_suffix('.original').write_bytes(data)
        path.with_suffix('.upload.json').write_text(json.dumps(orientation_info,indent=2))
        executor.submit(service.process,scan_id)
        return public_scan(store.scan(scan_id))

    @app.get('/sites/{site_id}/registry')
    def registry(site_id:str):
        require_site(site_id)
        return store.registry(site_id)

    @app.post('/sites/{site_id}/confirm-baseline')
    def confirm_baseline(site_id:str,request:EnrollmentRequest):
        require_site(site_id)
        try:
            return executor.submit(store.confirm_baseline,site_id,request.baseline_scan_id,
                                   [o.model_dump() for o in request.objects]).result()
        except ValueError as error:
            raise HTTPException(409,str(error))

    @app.post('/sites/{site_id}/objects/{object_id}/identity')
    def identity(site_id:str,object_id:str,request:IdentityRequest):
        require_site(site_id)
        if request.user_confirmed_name is None and request.ignored is None:
            raise HTTPException(422,'Provide a name or an ignore decision')
        try:
            return executor.submit(store.correct_identity,site_id,object_id,request.user_confirmed_name,request.ignored).result()
        except ValueError as error:
            raise HTTPException(409,str(error))

    @app.post('/sites/{site_id}/objects/{object_id}/link-identity')
    def link_identity(site_id:str,object_id:str,request:IdentityLinkRequest):
        require_site(site_id)
        try:
            return executor.submit(store.link_identity,site_id,object_id,request.member_id).result()
        except ValueError as error:
            raise HTTPException(409,str(error))

    @app.post('/scans/{scan_id}/verify-removal',status_code=202)
    def verify_removal(scan_id:str):
        scan=store.scan(scan_id)
        if scan is None:
            raise HTTPException(404,'Unknown scan')
        if scan['processing_status']!='complete' or scan['scan_type']!='comparison':
            raise HTTPException(409,'Choose a completed rescan')
        if not any(e['confirmed'] for e in store.registry(scan['site_id'],scan['session_id'])['objects']):
            raise HTTPException(409,'Confirm baseline objects first')
        review=store.removal_review(scan_id)
        if review and (review['status']=='queued' or any(c['accepted'] for c in review['checks'])):
            return review
        store.queue_removal_review(scan_id)
        executor.submit(service.review_removal,scan_id)
        return store.removal_review(scan_id)

    @app.get('/')
    def dashboard():
        return FileResponse(ROOT/'frontend'/'index.html')

    app.mount('/dashboard',StaticFiles(directory=ROOT/'frontend',html=True),name='dashboard')

    return app


app=create_app()
