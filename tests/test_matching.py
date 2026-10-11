"""Synthetic unit inputs test matching logic only, never vision accuracy."""
import unittest
from backend.matching import compare


def obj(name, label='bottle', center=(0.2, 0.2), vector=(1., 0.), color=(1., 0.), area=.05):
    return dict(id=name, label=label, center=list(center), embedding=list(vector),
                color=list(color), area=area, confidence=.9, bbox=[0, 0, 10, 10])


class MatchingTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(sum(compare([], [])['counts'].values()), 0)

    def test_identical(self):
        self.assertEqual(compare([obj('a')], [obj('b')])['counts']['UNCHANGED'], 1)

    def test_moved(self):
        self.assertEqual(compare([obj('a')], [obj('b', center=(.5, .2))])['counts']['MOVED'], 1)

    def test_added_removed(self):
        result = compare([obj('a')], [obj('b', label='chair')])
        self.assertEqual(result['counts']['ADDED'], 1)
        self.assertEqual(result['counts']['REMOVED'], 1)

    def test_visual_rejection(self):
        result = compare([obj('a')], [obj('b', vector=(0., 1.))])
        self.assertEqual(result['counts']['ADDED'], 1)
        self.assertEqual(result['counts']['REMOVED'], 1)

    def test_one_to_one(self):
        result = compare([obj('a')], [obj('b'), obj('c', center=(.6, .6))])
        self.assertEqual(result['counts']['UNCHANGED'], 1)
        self.assertEqual(result['counts']['ADDED'], 1)

    def test_ambiguity(self):
        result = compare([obj('a'), obj('b')], [obj('c'), obj('d')])
        self.assertTrue(all(e['needs_review'] for e in result['events']))

    def test_size_rejection(self):
        self.assertEqual(compare([obj('a')], [obj('b', area=.3)])['counts']['ADDED'], 1)


if __name__ == '__main__':
    unittest.main()
