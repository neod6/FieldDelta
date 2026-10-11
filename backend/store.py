from contextlib import contextmanager
from datetime import datetime,timezone
import json
from pathlib import Path
import sqlite3
import uuid


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self,path):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connection() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS accounts(id TEXT PRIMARY KEY,name TEXT NOT NULL,is_demo INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE IF NOT EXISTS sites(id TEXT PRIMARY KEY,account_id TEXT NOT NULL REFERENCES accounts(id),name TEXT NOT NULL,description TEXT NOT NULL DEFAULT '');
            CREATE TABLE IF NOT EXISTS scans(id TEXT PRIMARY KEY,site_id TEXT NOT NULL REFERENCES sites(id),timestamp TEXT NOT NULL,created_at TEXT NOT NULL,image_path TEXT NOT NULL,scan_type TEXT NOT NULL,processing_status TEXT NOT NULL,error TEXT,descriptor_json TEXT,result_json TEXT,previous_scan_id TEXT REFERENCES scans(id));
            CREATE TABLE IF NOT EXISTS scene_objects(id TEXT PRIMARY KEY,scan_id TEXT NOT NULL REFERENCES scans(id),stable_id TEXT NOT NULL,label TEXT NOT NULL,confidence REAL NOT NULL,bbox_json TEXT NOT NULL,position_json TEXT NOT NULL,matching_confidence REAL,verification_status TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS change_events(id TEXT PRIMARY KEY,site_id TEXT NOT NULL REFERENCES sites(id),previous_scan_id TEXT REFERENCES scans(id),current_scan_id TEXT NOT NULL REFERENCES scans(id),type TEXT NOT NULL,object_json TEXT NOT NULL,timestamp TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS scans_site ON scans(site_id,created_at);
            CREATE INDEX IF NOT EXISTS objects_scan ON scene_objects(scan_id);
            CREATE TABLE IF NOT EXISTS registry_objects(site_id TEXT NOT NULL REFERENCES sites(id),stable_id TEXT NOT NULL,label TEXT NOT NULL,status TEXT NOT NULL,confidence REAL,last_seen TEXT NOT NULL,last_seen_scan_id TEXT NOT NULL REFERENCES scans(id),last_assessed_scan_id TEXT NOT NULL REFERENCES scans(id),bbox_json TEXT NOT NULL,enrollment_status TEXT NOT NULL,PRIMARY KEY(site_id,stable_id));
            CREATE TABLE IF NOT EXISTS observations(scan_id TEXT NOT NULL REFERENCES scans(id),stable_id TEXT NOT NULL,detected_object_id TEXT,observed INTEGER NOT NULL,status TEXT NOT NULL,evidence_json TEXT NOT NULL,PRIMARY KEY(scan_id,stable_id));
            CREATE TABLE IF NOT EXISTS registry_enrollments(site_id TEXT NOT NULL REFERENCES sites(id),object_id TEXT NOT NULL,candidate_id TEXT NOT NULL,baseline_scan_id TEXT NOT NULL REFERENCES scans(id),display_name TEXT NOT NULL,confirmed_at TEXT NOT NULL,PRIMARY KEY(site_id,object_id));
            CREATE TABLE IF NOT EXISTS removal_reviews(scan_id TEXT PRIMARY KEY REFERENCES scans(id),status TEXT NOT NULL,created_at TEXT NOT NULL,result_json TEXT,error TEXT);
            CREATE TABLE IF NOT EXISTS cloud_reviews(scan_id TEXT PRIMARY KEY REFERENCES scans(id),created_at TEXT NOT NULL,result_json TEXT NOT NULL,evidence_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS object_corrections(site_id TEXT NOT NULL REFERENCES sites(id),stable_object_id TEXT NOT NULL,raw_ai_label TEXT NOT NULL,user_confirmed_name TEXT,confirmed_at TEXT NOT NULL,confirmed_by TEXT NOT NULL,ignored INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(site_id,stable_object_id));
            CREATE TABLE IF NOT EXISTS operator_identity_links(site_id TEXT NOT NULL REFERENCES sites(id),member_id TEXT NOT NULL,canonical_id TEXT NOT NULL,confirmed_at TEXT NOT NULL,source TEXT NOT NULL,PRIMARY KEY(site_id,member_id));
            ''')
            db.executemany('INSERT OR IGNORE INTO accounts(id,name) VALUES(?,?)',
                           [('demo-warehouse','Demo Warehouse'),('campus-lab','Campus Lab')])
            db.executemany('INSERT OR IGNORE INTO sites(id,account_id,name,description) VALUES(?,?,?,?)',
                          [('storage-a','demo-warehouse','Storage A','Demo inspection site'),
                           ('loading-area','demo-warehouse','Loading Area','Demo inspection site'),
                           ('desk-01','campus-lab','Desk 01','Demo inspection site'),
                           ('equipment-room','campus-lab','Equipment Room','Demo inspection site')])
        self.migrate_sessions()
        self.backfill_memory()

    def migrate_sessions(self):
        with self.connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS inspection_sessions(id TEXT PRIMARY KEY,site_id TEXT NOT NULL REFERENCES sites(id),created_at TEXT NOT NULL,baseline_scan_id TEXT REFERENCES scans(id),active INTEGER NOT NULL DEFAULT 1,legacy INTEGER NOT NULL DEFAULT 0);
                CREATE UNIQUE INDEX IF NOT EXISTS active_session_site ON inspection_sessions(site_id) WHERE active=1;
            ''')
            if 'session_id' not in {r['name'] for r in db.execute('PRAGMA table_info(scans)')}:
                db.execute('ALTER TABLE scans ADD COLUMN session_id TEXT REFERENCES inspection_sessions(id)')
            # Preserve original comparison lineage and results; do not invent historic baseline intent.
            for site in db.execute('SELECT DISTINCT site_id FROM scans WHERE session_id IS NULL').fetchall():
                rows=db.execute('SELECT * FROM scans WHERE site_id=? AND session_id IS NULL ORDER BY created_at,id',(site['site_id'],)).fetchall()
                sid='legacy-'+site['site_id']
                baseline=next((r['id'] for r in rows if r['scan_type']=='baseline'),None)
                db.execute('UPDATE inspection_sessions SET active=0 WHERE site_id=?',(site['site_id'],))
                db.execute('INSERT OR IGNORE INTO inspection_sessions VALUES(?,?,?,?,1,1)',(sid,site['site_id'],rows[0]['created_at'],baseline))
                db.execute('UPDATE scans SET session_id=? WHERE site_id=? AND session_id IS NULL',(sid,site['site_id']))

    def sessions(self,site_id):
        with self.connection() as db:
            rows=[dict(r) for r in db.execute('SELECT * FROM inspection_sessions WHERE site_id=? ORDER BY created_at,id',(site_id,))]
        return [{**r,'session_id':r['id'],'number':i+1} for i,r in reversed(list(enumerate(rows)))]

    def active_session(self,site_id):
        return next((s for s in self.sessions(site_id) if s['active']),None)

    def session_for_scan(self,scan_id):
        scan=self.scan(scan_id)
        return scan.get('session_id') if scan else None

    def registry_path(self,site_id,session_id=None):
        session_id=session_id or (self.active_session(site_id) or {}).get('id')
        root=Path(__file__).resolve().parents[1]/'data'/'sites'/site_id
        session=next((s for s in self.sessions(site_id) if s['id']==session_id),None)
        return root/'registry.json' if session and session['legacy'] else root/'sessions'/str(session_id)/'registry.json'

    @contextmanager
    def connection(self):
        db=sqlite3.connect(self.path,timeout=20)
        db.row_factory=sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def accounts(self):
        with self.connection() as db:
            return [dict(r) for r in db.execute('SELECT * FROM accounts ORDER BY id')]

    def sites(self,account_id=None):
        with self.connection() as db:
            rows=db.execute('SELECT s.*,EXISTS(SELECT 1 FROM scans x WHERE x.site_id=s.id AND x.processing_status="complete") AS has_baseline FROM sites s WHERE (? IS NULL OR account_id=?) ORDER BY s.id',(account_id,account_id))
            values=[dict(r) for r in rows]
        for value in values:
            session=self.active_session(value['id'])
            value['active_session_id']=session['id'] if session else None
            baseline=self.scan(session['baseline_scan_id']) if session and session['baseline_scan_id'] else None
            value['has_baseline']=int(bool(baseline and baseline['processing_status']=='complete'))
        return values

    def site(self,site_id):
        return next((s for s in self.sites() if s['id']==site_id),None)

    def scan(self,scan_id):
        with self.connection() as db:
            row=db.execute('SELECT * FROM scans WHERE id=?',(scan_id,)).fetchone()
            return dict(row) if row else None

    def scans(self,site_id):
        with self.connection() as db:
            return [dict(r) for r in db.execute('SELECT * FROM scans WHERE site_id=? ORDER BY created_at DESC',(site_id,))]

    def latest(self,site_id,exclude=None,session_id=None):
        excluded=self.scan(exclude) if exclude else None
        session_id=session_id or (excluded or {}).get('session_id') or (self.active_session(site_id) or {}).get('id')
        return next((s for s in self.scans(site_id) if s['session_id']==session_id and s['processing_status']=='complete' and s['id']!=exclude
                     and (excluded is None or s['created_at']<excluded['created_at'])),None)

    def create_scan(self,scan_id,site_id,timestamp,image_path,new_inspection=False,session_id=None):
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            active=db.execute('SELECT * FROM inspection_sessions WHERE site_id=? AND active=1',(site_id,)).fetchone()
            if session_id and (active is None or active['id']!=session_id):
                raise ValueError('Inspection changed. Select the site again before scanning.')
            if new_inspection or active is None:
                sid=str(uuid.uuid4())
                db.execute('UPDATE inspection_sessions SET active=0 WHERE site_id=?',(site_id,))
                db.execute('INSERT INTO inspection_sessions VALUES(?,?,?,NULL,1,0)',(sid,site_id,now()))
            else:
                sid=active['id']
                if db.execute('SELECT 1 FROM scans WHERE session_id=? AND processing_status IN ("queued","processing","cloud_processing")',(sid,)).fetchone():
                    raise ValueError('Wait for the current scan to finish before continuing this inspection.')
                baseline=db.execute('SELECT processing_status FROM scans WHERE id=?',(active['baseline_scan_id'],)).fetchone()
                if baseline is None or baseline['processing_status']!='complete':
                    raise ValueError('Baseline is not ready. Start a new inspection or wait for processing.')
            db.execute('INSERT INTO scans(id,site_id,timestamp,created_at,image_path,scan_type,processing_status,session_id) VALUES(?,?,?,?,?,"pending","queued",?)',
                       (scan_id,site_id,timestamp,now(),str(image_path),sid))
            db.execute('UPDATE inspection_sessions SET baseline_scan_id=? WHERE id=? AND baseline_scan_id IS NULL',(scan_id,sid))

    def status(self,scan_id,status,error=None):
        with self.connection() as db:
            db.execute('UPDATE scans SET processing_status=?,error=? WHERE id=?',(status,error,scan_id))

    def objects(self,scan_id):
        with self.connection() as db:
            rows=[dict(r) for r in db.execute('SELECT * FROM scene_objects WHERE scan_id=?',(scan_id,))]
        for row in rows:
            row['bbox']=json.loads(row.pop('bbox_json'))
            row['position']=json.loads(row.pop('position_json'))
        return rows

    def finish(self,scan_id,descriptor,result,previous_id,ids):
        scan=self.scan(scan_id)
        if previous_id and self.session_for_scan(previous_id)!=scan['session_id']:
            raise ValueError('Cannot compare scans across inspection sessions')
        with self.connection() as db:
            db.execute('UPDATE scans SET processing_status="complete",scan_type=?,descriptor_json=?,result_json=?,previous_scan_id=? WHERE id=?',
                       ('comparison' if previous_id else 'baseline',json.dumps(descriptor),json.dumps(result),previous_id,scan_id))
            for obj in descriptor['objects']:
                db.execute('INSERT INTO scene_objects VALUES(?,?,?,?,?,?,?,?,?)',
                           (obj['id'],scan_id,ids[obj['id']],obj['label'],obj['confidence'],
                            json.dumps(obj['normalized_bbox']),json.dumps(obj['center']),None,'PROVISIONAL'))
            for event in result.get('events',[]):
                if event['type'] in ('ADDED','REMOVED','MOVED','UNCERTAIN'):
                    db.execute('INSERT INTO change_events VALUES(?,?,?,?,?,?,?)',
                               (str(uuid.uuid4()),scan['site_id'],previous_id,scan_id,event['type'],json.dumps(event),scan['timestamp']))
            self._record_memory(db, {**scan, 'result_json':json.dumps(result),
                                    'previous_scan_id':previous_id})

    def local_evidence(self,scan_id):
        path=Path(__file__).resolve().parents[1]/'results'/'product_scans'/scan_id/'local.json'
        return json.loads(path.read_text()) if path.exists() else None

    def cloud_evidence(self,scan_id):
        with self.connection() as db:
            review=db.execute('SELECT evidence_json,created_at FROM cloud_reviews WHERE scan_id=?',(scan_id,)).fetchone()
        if review:
            return dict(**json.loads(review['evidence_json']),verification_rerun_at=review['created_at'])
        path=Path(__file__).resolve().parents[1]/'results'/'product_scans'/scan_id/'cloud.json'
        if not path.exists():
            error_path=path.with_name('cloud_error.json')
            return json.loads(error_path.read_text()) if error_path.exists() else None
        value=json.loads(path.read_text())
        return {key:value.get(key) for key in ('result','http_status','latency_seconds','transport_attempts','provider','model','usage')}

    def save_cloud_review(self,scan_id,result,evidence):
        with self.connection() as db:
            db.execute('INSERT INTO cloud_reviews VALUES(?,?,?,?) ON CONFLICT(scan_id) DO UPDATE SET created_at=excluded.created_at,result_json=excluded.result_json,evidence_json=excluded.evidence_json',
                       (scan_id,now(),json.dumps(result),json.dumps(evidence)))

    def registry(self,site_id,session_id=None):
        value=self.load_registry(site_id,session_id)
        if value is None:
            return dict(status='NO_BASELINE',objects=[])
        baseline=next((s for s in self.scans(site_id) if s['image_path']==value['reference_image']),None)
        return dict(status=value['status'],baseline_scan_id=baseline['id'] if baseline else None,
                    objects=[dict(object_id=e['object_id'],candidate_id=e['reference']['id'],display_name=e['display_name'],
                    confirmed=e['confirmed'],state=e['state'],bbox=e.get('enrollment_reference',e['reference'])['normalized_bbox'],
                    **self.identity(site_id,e['object_id'])) for e in value['objects']])

    def identity(self,site_id,object_id):
        object_id=object_id.removeprefix('cloud:')
        with self.connection() as db:
            link=db.execute('SELECT canonical_id FROM operator_identity_links WHERE site_id=? AND member_id=?',(site_id,object_id)).fetchone()
            canonical=link['canonical_id'] if link else object_id
            row=db.execute('SELECT * FROM object_corrections WHERE site_id=? AND stable_object_id=?',(site_id,object_id)).fetchone()
            shared=db.execute('SELECT * FROM object_corrections WHERE site_id=? AND stable_object_id=?',(site_id,canonical)).fetchone() if link else row
        if shared:
            return {**dict(shared),'raw_ai_label':row['raw_ai_label'] if row else shared['raw_ai_label'],'canonical_id':canonical}
        return dict(row) if row else {}

    def link_identity(self,site_id,canonical_id,member_id):
        """Explicit operator association only; never infer identity from detector class."""
        if canonical_id==member_id:
            raise ValueError('Choose two different observations')
        with self.connection() as db:
            sessions=[]
            for oid in (canonical_id,member_id):
                rows=db.execute('SELECT DISTINCT s.session_id FROM scene_objects o JOIN scans s ON o.scan_id=s.id WHERE s.site_id=? AND o.stable_id=?',(site_id,oid)).fetchall()
                sessions.append({r['session_id'] for r in rows})
            if not sessions[0].intersection(sessions[1]):
                raise ValueError('Both observations must belong to the same site and inspection')
            if db.execute('SELECT 1 FROM operator_identity_links WHERE site_id=? AND (member_id=? OR canonical_id=?)',(site_id,canonical_id,member_id)).fetchone():
                raise ValueError('Identity links cannot form chains or cycles')
            old=db.execute('SELECT canonical_id FROM operator_identity_links WHERE site_id=? AND member_id=?',(site_id,member_id)).fetchone()
            if old and old['canonical_id']!=canonical_id:
                raise ValueError('Observation already belongs to another identity')
            db.execute('INSERT OR IGNORE INTO operator_identity_links VALUES(?,?,?,?,?)',(site_id,member_id,canonical_id,now(),'operator_confirmed_identity'))
        return self.identity(site_id,member_id)

    def correct_identity(self,site_id,object_id,name=None,ignored=None):
        object_id=self.identity(site_id,object_id).get('canonical_id',object_id)
        if name is not None and (not name.strip() or len(name)>100):
            raise ValueError('Enter an object name with 1-100 characters')
        with self.connection() as db:
            obj=db.execute('SELECT label,enrollment_status FROM registry_objects WHERE site_id=? AND stable_id=?',(site_id,object_id)).fetchone()
            if obj is None:
                raise ValueError('Unknown registry object for this site')
            if ignored and obj['enrollment_status']=='CONFIRMED':
                raise ValueError('A tracked object cannot be ignored as detector noise')
            old=db.execute('SELECT * FROM object_corrections WHERE site_id=? AND stable_object_id=?',(site_id,object_id)).fetchone()
            raw=db.execute('SELECT label FROM scene_objects WHERE stable_id=? AND scan_id IN (SELECT id FROM scans WHERE site_id=?) ORDER BY rowid LIMIT 1',(object_id,site_id)).fetchone()
            values=(site_id,object_id,old['raw_ai_label'] if old else raw['label'] if raw else obj['label'],
                    name.strip() if name is not None else old['user_confirmed_name'] if old else None,now(),'demo_operator',
                    int(ignored) if ignored is not None else old['ignored'] if old else 0)
            db.execute('INSERT INTO object_corrections VALUES(?,?,?,?,?,?,?) ON CONFLICT(site_id,stable_object_id) DO UPDATE SET user_confirmed_name=excluded.user_confirmed_name,confirmed_at=excluded.confirmed_at,confirmed_by=excluded.confirmed_by,ignored=excluded.ignored',values)
        return self.identity(site_id,object_id)

    def load_registry(self,site_id,session_id=None):
        path=self.registry_path(site_id,session_id)
        if not path.exists():
            return None
        value=json.loads(path.read_text())
        baseline=next((s for s in self.scans(site_id) if s['scan_type']=='baseline' and s['image_path']==value['reference_image']),None)
        # Explicit review may include proposals outside the automatic ROI.
        # These remain provisional, and the matching ROI is unchanged.
        if baseline:
            descriptor=json.loads(baseline['descriptor_json'] or '{}')
            stable={o['id']:o['stable_id'] for o in self.objects(baseline['id'])}
            existing={e['reference']['id'] for e in value['objects']}
            for obj in descriptor.get('objects',[]):
                if obj['id'] in existing or obj['id'] not in stable:
                    continue
                value['objects'].append(dict(object_id=stable[obj['id']],display_name=obj['label'],confirmed=False,
                    reference=obj,reference_embeddings=[obj.get('embedding',[])],reference_crops=[obj.get('crop_path')],
                    semantic_suggestions=obj.get('semantic_suggestions',[obj['label']]),last_known_position=obj['center'],
                    last_seen_timestamp=baseline['timestamp'],state='ENROLLMENT_CANDIDATE'))
        with self.connection() as db:
            names={r['object_id']:dict(r) for r in db.execute('SELECT * FROM registry_enrollments WHERE site_id=?',(site_id,))}
            states={r['stable_id']:r['status'] for r in db.execute('SELECT stable_id,status FROM registry_objects WHERE site_id=?',(site_id,))}
        for entry in value['objects']:
            enrolled=names.get(entry['object_id'])
            entry['confirmed']=enrolled is not None
            if enrolled:
                entry['display_name']=enrolled['display_name']
                entry['state']=states.get(entry['object_id'],'CONFIRMED')
                entry.setdefault('enrollment_reference',dict(entry['reference']))
            correction=self.identity(site_id,entry['object_id'])
            if correction.get('user_confirmed_name'):
                entry['display_name']=correction['user_confirmed_name']
        value['status']='ENROLLED' if any(e['confirmed'] for e in value['objects']) else 'AWAITING_USER_CONFIRMATION'
        return value

    def confirm_baseline(self,site_id,baseline_id,selections):
        scan=self.scan(baseline_id)
        registry=self.load_registry(site_id,scan.get('session_id') if scan else None)
        if not scan or scan['site_id']!=site_id or scan['scan_type']!='baseline' or scan['processing_status']!='complete':
            raise ValueError('Choose a completed baseline for this site')
        if registry is None or registry['reference_image']!=scan['image_path']:
            raise ValueError('Baseline is not the active registry reference')
        candidates={e['object_id']:e for e in registry['objects']}
        if not selections or len(selections)>50 or len({s['object_id'] for s in selections})!=len(selections):
            raise ValueError('Select distinct baseline candidates')
        if any(s['object_id'] not in candidates or not s['display_name'].strip() or len(s['display_name'])>100 for s in selections):
            raise ValueError('Select valid candidates with short non-empty names')
        if any(self.identity(site_id,s['object_id']).get('ignored') for s in selections):
            raise ValueError('Restore ignored candidates before confirming them')
        with self.connection() as db:
            for selection in selections:
                entry=candidates[selection['object_id']]
                db.execute('INSERT INTO registry_enrollments VALUES(?,?,?,?,?,?) ON CONFLICT(site_id,object_id) DO UPDATE SET display_name=excluded.display_name',
                           (site_id,entry['object_id'],entry['reference']['id'],baseline_id,selection['display_name'].strip(),now()))
                db.execute('UPDATE registry_objects SET enrollment_status="CONFIRMED",label=? WHERE site_id=? AND stable_id=?',
                           (selection['display_name'].strip(),site_id,entry['object_id']))
        for selection in selections:
            self.correct_identity(site_id,selection['object_id'],selection['display_name'])
        return self.registry(site_id,scan['session_id'])

    def removal_review(self,scan_id):
        with self.connection() as db:
            row=db.execute('SELECT * FROM removal_reviews WHERE scan_id=?',(scan_id,)).fetchone()
        if row is None:
            return None
        value=dict(row)
        value['checks']=json.loads(value.pop('result_json') or '[]')
        return value

    def queue_removal_review(self,scan_id):
        with self.connection() as db:
            db.execute('INSERT INTO removal_reviews VALUES(?,"queued",?,NULL,NULL) ON CONFLICT(scan_id) DO UPDATE SET status="queued",created_at=excluded.created_at,result_json=NULL,error=NULL',
                       (scan_id,now()))

    def save_removal_review(self,scan_id,checks,error=None):
        scan=self.scan(scan_id)
        with self.connection() as db:
            db.execute('UPDATE removal_reviews SET status=?,result_json=?,error=? WHERE scan_id=?',
                       ('failed' if error else 'complete',json.dumps(checks),error,scan_id))
            for check in checks:
                if not check['accepted']:
                    continue
                existing=db.execute('SELECT 1 FROM change_events WHERE current_scan_id=? AND type="REMOVED" AND json_extract(object_json,"$.object_id")=?',(scan_id,check['object_id'])).fetchone()
                if not existing:
                    event=dict(object_id=check['object_id'],label=check['label'],type='REMOVED',reason='CONTROLLED_REMOVAL_VERIFIED',evidence=check['evidence'],verified_at=now())
                    db.execute('INSERT INTO change_events VALUES(?,?,?,?,?,?,?)',
                        (str(uuid.uuid4()),scan['site_id'],scan['previous_scan_id'],scan_id,'REMOVED',json.dumps(event),scan['timestamp']))
                # An old-scan review must not overwrite a more recent observation.
                db.execute('UPDATE registry_objects SET status="REMOVED" WHERE site_id=? AND stable_id=? AND last_assessed_scan_id=?',
                           (scan['site_id'],check['object_id'],scan_id))
                db.execute('UPDATE observations SET status="REMOVED",evidence_json=? WHERE scan_id=? AND stable_id=?',
                           (json.dumps(dict(source='controlled_removal_review',decision=check)),scan_id,check['object_id']))

    def public_scan(self,scan):
        value=public_scan(scan)
        with self.connection() as db:
            cloud=db.execute('SELECT result_json,created_at FROM cloud_reviews WHERE scan_id=?',(scan['id'],)).fetchone()
        if cloud:
            value['result']=json.loads(cloud['result_json'])
            value['cloud_verification_rerun_at']=cloud['created_at']
        review=self.removal_review(scan['id'])
        value['removal_review']=review
        if review and review['status']=='complete' and value['result'] is not None:
            from .removal import apply_checks
            value['result']=apply_checks(value['result'],review['checks'])
        value['object_results']=self.object_results(scan,value.get('result') or {})
        return value

    def object_results(self,scan,result):
        """Presentation-only flags: possibly missing never becomes a stored REMOVED event."""
        items={}
        for event in result.get('events',[]):
            oid=event.get('object_id')
            if oid:
                items[oid]=dict(object_id=oid,label=event.get('label','Unknown'),status=event['type'],reason=event.get('reason','Needs review'))
        checks=(self.removal_review(scan['id']) or {}).get('checks') or result.get('controlled_removal',[])
        for check in checks:
            evidence=check.get('evidence',{})
            strong=evidence.get('max_local_dino_similarity',1)>=.75
            if evidence.get('confirmed') and not strong:
                items[check['object_id']]=dict(object_id=check['object_id'],label=check['label'],
                    status='REMOVED' if check['accepted'] else 'POSSIBLY_MISSING',reason='Verified absence' if check['accepted'] else 'Needs review')
        observations={o['stable_id']:o for o in self.observations(scan['id'])}
        for entry in self.registry(scan['site_id'],scan['session_id'])['objects']:
            if scan['scan_type']=='baseline':
                items[entry['object_id']]=dict(object_id=entry['object_id'],label=entry['display_name'],
                    status='UNCERTAIN',reason='Baseline candidate; confirm on desktop')
            item=items.get(entry['object_id'])
            if entry['confirmed'] and item is None and entry['object_id'] in observations:
                observation=observations[entry['object_id']]
                if not observation['observed']:
                    item=dict(object_id=entry['object_id'],label=entry['display_name'],status='UNCERTAIN',reason='Tracked identity was not assessed in this scan; needs review')
                    items[entry['object_id']]=item
            if entry['confirmed'] and item and item['status']=='UNCERTAIN':
                event=next((e for e in result.get('events',[]) if e.get('object_id')==entry['object_id']),{})
                if event.get('local_type')=='NOT_OBSERVED':
                    item.update(label=entry['display_name'],status='POSSIBLY_MISSING',reason='Needs review')
            if entry['confirmed'] and item:
                item['enrollment_status']='CONFIRMED'
        for item in items.values():
            correction=self.identity(scan['site_id'],item['object_id'])
            if correction.get('user_confirmed_name'):
                item['raw_ai_label']=item['label']
                item['label']=correction['user_confirmed_name']
                item['user_confirmed_name']=correction['user_confirmed_name']
                event=next((e for e in result.get('events',[]) if e.get('object_id')==item['object_id']),{})
                if item['status']=='UNCERTAIN' and event.get('local_type')=='NOT_OBSERVED':
                    item.update(status='POSSIBLY_MISSING',reason='Not observed; absence has not been verified')
        return [item for item in items.values()
                if not self.identity(scan['site_id'],item['object_id']).get('ignored')
                and (item['status'] in ('ADDED','REMOVED','MOVED','UNCHANGED','POSSIBLY_MISSING')
                     or item.get('enrollment_status')=='CONFIRMED' or item.get('user_confirmed_name'))]

    def product_objects(self,scan):
        """Use recorded fusion decisions and enrollment, never a cosmetic score cutoff."""
        results={o['object_id']:o for o in self.public_scan(scan)['object_results']}
        confirmed={e['object_id'] for e in self.registry(scan['site_id'],scan['session_id'])['objects'] if e['confirmed']}
        rows=[]
        for obj in self.objects(scan['id']):
            identity=self.identity(scan['site_id'],obj['stable_id'])
            decision=results.get(obj['stable_id'],{})
            if identity.get('ignored') or (not identity.get('user_confirmed_name') and obj['stable_id'] not in confirmed and decision.get('status') not in ('ADDED','MOVED','UNCHANGED')):
                continue
            rows.append({**obj,'raw_ai_label':obj['label'],'label':identity.get('user_confirmed_name') or obj['label'],'canonical_id':identity.get('canonical_id',obj['stable_id'])})
        return rows

    def _record_memory(self,db,scan):
        """Project saved evidence into memory, without upgrading uncertain decisions."""
        result=json.loads(scan['result_json'] or '{}')
        events={e.get('object_id'):e for e in result.get('events',[]) if e.get('object_id')}
        local=self.local_evidence(scan['id']) or {}
        local_events={e.get('object_id'):e for e in local.get('events',[]) if e.get('object_id')}
        enrollment={e['object_id']:e for e in self.registry(scan['site_id'],scan.get('session_id'))['objects']}
        detected=list(db.execute('SELECT * FROM scene_objects WHERE scan_id=?',(scan['id'],)))
        seen={o['stable_id'] for o in detected}
        for obj in detected:
            stable=obj['stable_id']
            event=events.get(stable,{})
            le=local_events.get(stable,{})
            status=event.get('type') or ('UNKNOWN' if le.get('type')=='UNKNOWN' else 'OBSERVED_CANDIDATE')
            enrolled=enrollment.get(stable)
            enrollment_status=('CONFIRMED' if enrolled['confirmed'] else 'ENROLLMENT_CANDIDATE') if enrolled else 'NOT_ENROLLED'
            db.execute('''INSERT INTO registry_objects VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(site_id,stable_id) DO UPDATE SET label=excluded.label,status=excluded.status,
                confidence=excluded.confidence,last_seen=excluded.last_seen,last_seen_scan_id=excluded.last_seen_scan_id,
                last_assessed_scan_id=excluded.last_assessed_scan_id,bbox_json=excluded.bbox_json,enrollment_status=excluded.enrollment_status''',
                (scan['site_id'],stable,enrolled['display_name'] if enrolled else obj['label'],status,obj['confidence'],scan['timestamp'],scan['id'],scan['id'],obj['bbox_json'],enrollment_status))
            evidence=dict(source='saved_detector_observation',local=le,decision=event,
                          detector_confidence=obj['confidence'],identity_is_provisional=True)
            db.execute('INSERT OR IGNORE INTO observations VALUES(?,?,?,?,?,?)',
                       (scan['id'],stable,obj['id'],1,status,json.dumps(evidence)))
        previous=list(db.execute('SELECT r.stable_id,r.status FROM registry_objects r JOIN scans s ON r.last_seen_scan_id=s.id WHERE r.site_id=? AND s.session_id=?',(scan['site_id'],scan.get('session_id'))))
        for row in previous:
            stable=row['stable_id']
            if stable in seen:
                continue
            event=events.get(stable,{})
            le=local_events.get(stable,{})
            status='REMOVED' if event.get('type')=='REMOVED' else ('NOT_OBSERVED' if le.get('type')=='NOT_OBSERVED' or event.get('local_type')=='NOT_OBSERVED' else 'NOT_ASSESSED')
            if row['status']=='REMOVED' and event.get('type')!='MOVED' and event.get('type')!='UNCHANGED':
                status='REMOVED'
            db.execute('UPDATE registry_objects SET status=?,last_assessed_scan_id=? WHERE site_id=? AND stable_id=?',
                       (status,scan['id'],scan['site_id'],stable))
            db.execute('INSERT OR IGNORE INTO observations VALUES(?,?,?,?,?,?)',
                       (scan['id'],stable,None,0,status,json.dumps(dict(source='saved_history_projection',local=le,decision=event,
                       limitation='Missing observation is not proof of removal'))))
        # Preserve every recorded decision category; never invent a change from a missing detection.
        for event in result.get('events',[]):
            payload=json.dumps(event)
            if not db.execute('SELECT 1 FROM change_events WHERE current_scan_id=? AND type=? AND object_json=?',
                              (scan['id'],event['type'],payload)).fetchone():
                db.execute('INSERT INTO change_events VALUES(?,?,?,?,?,?,?)',
                           (str(uuid.uuid4()),scan['site_id'],scan.get('previous_scan_id'),scan['id'],event['type'],payload,scan['timestamp']))

    def backfill_memory(self):
        with self.connection() as db:
            for scan in db.execute('SELECT * FROM scans WHERE processing_status="complete" ORDER BY created_at,id').fetchall():
                if not db.execute('SELECT 1 FROM observations WHERE scan_id=? LIMIT 1',(scan['id'],)).fetchone():
                    self._record_memory(db,dict(scan))

    def memory(self,site_id,session_id=None):
        session_id=session_id or (self.active_session(site_id) or {}).get('id')
        with self.connection() as db:
            rows=[dict(r) for r in db.execute('SELECT r.* FROM registry_objects r JOIN scans s ON r.last_seen_scan_id=s.id WHERE r.site_id=? AND s.session_id=? ORDER BY r.last_seen DESC,r.label',(site_id,session_id))]
        for row in rows:
            row['bbox']=json.loads(row.pop('bbox_json'))
            row['presence']='REMOVED' if row['status']=='REMOVED' else ('OBSERVED_CANDIDATE' if row['last_seen_scan_id']==row['last_assessed_scan_id'] else 'UNKNOWN')
            identity=self.identity(site_id,row['stable_id'])
            row['raw_ai_label']=row['label']
            row.update(identity)
            if identity.get('user_confirmed_name'):
                row['label']=identity['user_confirmed_name']
        return rows

    def observations(self,scan_id):
        with self.connection() as db:
            rows=[dict(r) for r in db.execute('SELECT * FROM observations WHERE scan_id=? ORDER BY stable_id',(scan_id,))]
        for row in rows:
            row['evidence']=json.loads(row.pop('evidence_json'))
        return rows

    def recover(self):
        with self.connection() as db:
            db.execute('UPDATE scans SET processing_status="queued" WHERE processing_status IN ("processing","cloud_processing")')
            return [r['id'] for r in db.execute('SELECT id FROM scans WHERE processing_status="queued" ORDER BY created_at')]


def public_scan(scan):
    return dict(id=scan['id'],site_id=scan['site_id'],timestamp=scan['timestamp'],
                session_id=scan.get('session_id'),
                scan_type=scan['scan_type'],processing_status=scan['processing_status'],error=scan['error'],
                previous_scan_id=scan['previous_scan_id'],image_url=f'/scans/{scan["id"]}/image',
                result=json.loads(scan['result_json']) if scan['result_json'] else None)
