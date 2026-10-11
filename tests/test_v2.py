import unittest
import numpy as np
from PIL import Image
from backend.v2.registration import register, warp_points, inside_roi
from backend.v2.tracking import track, enrollment_candidates,confirm_registry,observe_registry

ROI=[[0,0],[1,0],[1,1],[0,1]]
REG=dict(matrix=np.eye(3).tolist(),reliable=True)


def obj(name,label='can',center=(.4,.4),vector=(1.,0.)):
    x,y=center
    return dict(id=name,label=label,center=list(center),normalized_bbox=[x-.04,y-.05,x+.04,y+.05],
                embedding=list(vector),color=[1.,0.],confidence=.8)


class V2Tests(unittest.TestCase):
    def test_soft_label(self):
        result=track([obj('a','cup')],[obj('b','bottle')],REG,ROI)
        self.assertEqual(result['counts']['UNCHANGED'],1)
        self.assertTrue(result['events'][0]['evidence']['semantic_mismatch'])

    def test_registration_uncertain(self):
        result=track([obj('a')],[obj('b',center=(.7,.4))],{**REG,'reliable':False},ROI)
        self.assertEqual(result['counts']['MOVED'],0)
        self.assertEqual(result['counts']['UNKNOWN'],1)

    def test_compensated_motion(self):
        matrix=np.eye(3)
        matrix[0,2]=-.2
        result=track([obj('a')],[obj('b',center=(.6,.4))],dict(matrix=matrix.tolist(),reliable=True),ROI)
        self.assertEqual(result['counts']['UNCHANGED'],1)

    def test_missing_not_removed(self):
        result=track([obj('a')],[],REG,ROI)
        self.assertEqual(result['counts']['REMOVED'],0)
        self.assertEqual(result['counts']['NOT_OBSERVED'],1)

    def test_unseen_candidate_not_added(self):
        self.assertEqual(track([],[obj('b')],REG,ROI)['counts']['UNKNOWN'],1)

    def test_two_same_label_identities(self):
        result=track([obj('a','mouse',vector=(1.,0.)),obj('b','mouse',center=(.7,.4),vector=(0.,1.))],
                     [obj('c','mouse',center=(.7,.4),vector=(0.,1.)),obj('d','mouse',vector=(1.,0.))],REG,ROI)
        self.assertEqual(result['counts']['UNCHANGED'],2)
        self.assertEqual({(e['before_id'],e['after_id']) for e in result['events']},{('a','d'),('b','c')})

    def test_roi(self):
        self.assertFalse(inside_roi([.5,.1],[[0,.3],[1,.3],[1,1],[0,1]]))

    def test_blank_registration(self):
        result=register(Image.new('RGB',(400,300)),Image.new('RGB',(400,300)))
        self.assertFalse(result['reliable'])
        self.assertEqual(result['status'],'REGISTRATION_UNCERTAIN')

    def test_warp(self):
        self.assertTrue(np.allclose(warp_points([[.3,.5]],np.eye(3)),[[.3,.5]]))

    def test_registry_stable_and_confirmation(self):
        scan=dict(image_path='/example/baseline.jpg',timestamp='baseline',objects=[obj('a')])
        entries=enrollment_candidates(scan,ROI)
        self.assertEqual(entries[0]['object_id'],enrollment_candidates(scan,ROI)[0]['object_id'])
        registry=dict(objects=entries,roi=ROI)
        self.assertEqual(observe_registry(registry,scan,REG)['status'],'AWAITING_USER_CONFIRMATION')
        confirm_registry(registry,{'a':'Silver can'})
        event=observe_registry(registry,{**scan,'timestamp':'second','objects':[obj('b','cup')]},REG)['events'][0]
        self.assertEqual(event['object_id'],entries[0]['object_id'])
        self.assertEqual(entries[0]['last_seen_timestamp'],'second')
        self.assertEqual(entries[0]['display_name'],'Silver can')

    def test_registry_unknown_preserves_last_seen(self):
        scan=dict(image_path='/example/baseline.jpg',timestamp='baseline',objects=[obj('a')])
        registry=dict(objects=enrollment_candidates(scan,ROI),roi=ROI)
        confirm_registry(registry,{'a':'Silver can'})
        observe_registry(registry,{**scan,'timestamp':'later','objects':[]},REG)
        self.assertEqual(registry['objects'][0]['state'],'NOT_OBSERVED')
        self.assertEqual(registry['objects'][0]['last_seen_timestamp'],'baseline')


if __name__=='__main__':
    unittest.main()
