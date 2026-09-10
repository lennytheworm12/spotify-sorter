"""Synthetic engineering checks; these do not validate musical classifications."""
import copy,json, unittest
from pathlib import Path
from mapper_reference import Mapper,normalize
CONFIG=json.loads(Path(__file__).with_name('genre-neighborhood-map-v1.json').read_text())
M=Mapper(CONFIG)
def profile(style=None,secondary=None,family=None,secondary_families=None,**extra):
    return M.profile(dict(primary_style=style,secondary_styles=secondary or [],primary_family=family,secondary_families=secondary_families or [],**extra))
class MappingTests(unittest.TestCase):
 def test_01_ids_unique(self):self.assertEqual(len(CONFIG['concepts']),len(M.concepts))
 def test_02_all_source_references(self):
    self.assertTrue(all(set(c['sources'])<=set(CONFIG['sources']) for c in CONFIG['concepts']))
 def test_03_rnb_aliases(self):
    for x in ['R&B','rnb','RnB','R & B','Rhythm and Blues']:self.assertEqual(M.resolve(x)['concept_ids'],['family:rnb_soul'])
 def test_04_hyphen_case(self):self.assertEqual(M.resolve('LO-FI HIP HOP')['concept_ids'],M.resolve('lo_fi_hip_hop')['concept_ids'])
 def test_05_dnb_aliases(self):
    for x in ['DnB','D&B','Drum & Bass','drum and bass']:self.assertEqual(M.resolve(x)['concept_ids'],['style:drum_and_bass'])
 def test_06_afrobeat_not_afrobeats(self):self.assertNotEqual(M.resolve('Afrobeat')['concept_ids'],M.resolve('Afrobeats')['concept_ids'])
 def test_07_lofi_not_lofi_hiphop(self):self.assertNotEqual(M.resolve('lo-fi')['concept_ids'],M.resolve('lo-fi hip-hop')['concept_ids'])
 def test_08_chillwave_not_chillhop(self):self.assertNotEqual(M.resolve('chillwave')['concept_ids'],M.resolve('chillhop')['concept_ids'])
 def test_09_hyperpop_not_electropop(self):self.assertNotEqual(M.resolve('hyperpop')['concept_ids'],M.resolve('electropop')['concept_ids'])
 def test_10_soul_not_rnb_alias(self):self.assertNotEqual(M.resolve('soul')['concept_ids'],M.resolve('rnb')['concept_ids'])
 def test_11_electronica_not_electronic_alias(self):self.assertNotEqual(M.resolve('electronica')['concept_ids'],M.resolve('electronic')['concept_ids'])
 def test_12_subgenre_not_parent_alias(self):self.assertNotEqual(M.resolve('Neo Soul')['concept_ids'],M.resolve('R&B')['concept_ids'])
 def test_13_raw_preserved(self):
    raw={'primary_family':'  R&B  ','primary_style':'Alt-R&B','secondary_families':['Pop'],'secondary_styles':['neo_soul']};before=copy.deepcopy(raw)
    got=M.profile(raw);self.assertEqual(raw,before);self.assertEqual(got['raw_genre_fields'],raw)
 def test_14_order_independence(self):
    self.assertEqual(profile('Trap',['Cloud Rap','Emo Rap'])['neighborhood_memberships'],profile('Trap',['Emo Rap','Cloud Rap'])['neighborhood_memberships'])
 def test_15_alias_dedup(self):
    self.assertEqual(profile('Trip Hop',['Trip-Hop','Trip Hop'])['neighborhood_memberships'],profile('Trip Hop')['neighborhood_memberships'])
 def test_16_unknown_noop(self):self.assertEqual(profile('new unheard microstyle')['neighborhood_memberships'],{})
 def test_17_missing_noop(self):self.assertEqual(profile()['neighborhood_memberships'],{})
 def test_18_empty_noop(self):self.assertEqual(profile('')['neighborhood_memberships'],{})
 def test_19_broad_pop_noop(self):self.assertEqual(profile('Pop',family='Electronic')['neighborhood_memberships'],{})
 def test_20_generic_experimental_noop(self):self.assertEqual(profile('Experimental')['neighborhood_memberships'],{})
 def test_21_context_only_noop(self):self.assertEqual(profile('K-Pop')['neighborhood_memberships'],{})
 def test_22_scene_does_not_change_sonic_profile(self):
    self.assertEqual(profile('Contemporary R&B',['K-Pop'])['neighborhood_memberships'],profile('Contemporary R&B',['Mandopop'])['neighborhood_memberships'])
 def test_23_all_electronic_not_dance(self):self.assertEqual(profile('Dance/Electronic')['neighborhood_memberships'],{})
 def test_24_hyperpop_not_ambient(self):self.assertNotIn('ambient_drone',profile('Hyperpop')['neighborhood_memberships'])
 def test_25_instrumental_not_lofi(self):self.assertNotIn('lofi_chillhop',profile('Instrumental Hip-Hop')['neighborhood_memberships'])
 def test_26_neurofunk_not_funk(self):self.assertNotIn('funk',profile('Neurofunk')['families'])
 def test_27_future_bass_not_techno(self):self.assertNotIn('techno',profile('Future Bass')['neighborhood_memberships'])
 def test_28_rnb_substyles_overlap(self):
    self.assertEqual(profile('Alternative R&B')['neighborhood_memberships']['rnb_soul'],1)
    self.assertEqual(profile('Neo Soul')['neighborhood_memberships']['rnb_soul'],1)
 def test_29_lofi_boom_bap_related_not_identical(self):
    a=profile('Lo-Fi Hip Hop')['neighborhood_memberships'];b=profile('Boom Bap')['neighborhood_memberships']
    self.assertNotEqual(a,b);self.assertTrue(set(a)&set(b))
 def test_30_unknown_does_not_penalize_known(self):
    self.assertEqual(profile('Neo Soul',['imaginary microstyle'])['neighborhood_memberships'],profile('Neo Soul')['neighborhood_memberships'])
 def test_31_specific_style_in_family_field(self):self.assertEqual(profile(family='Ambient')['neighborhood_memberships'],{'ambient_drone':.5})
 def test_32_wrong_type_rejected(self):
    with self.assertRaises(ValueError):M.profile({'secondary_styles':'Neo Soul'})
 def test_33_no_fuzzy_guess(self):self.assertEqual(M.resolve('hard technno')['status'],'unmapped')
 def test_34_no_arbitrary_slash_split(self):self.assertEqual(M.resolve('Ambient/Shoegaze')['status'],'unmapped')
 def test_35_review_required_compound(self):self.assertEqual(M.resolve('African Dancehall and Reggae')['status'],'review_required')
 def test_36_mapping_review_gate(self):self.assertEqual(profile('Digicore')['neighborhood_memberships'],{})
 def test_37_metadata_not_classifier(self):
    self.assertEqual(profile('Ambient',artist='Lil Uzi Vert',vocal_role='rap_led')['neighborhood_memberships'],profile('Ambient')['neighborhood_memberships'])
 def test_38_no_score_implemented(self):self.assertIsNone(profile('Neo Soul')['score_adjustment'])
 def test_39_deterministic_replay(self):self.assertEqual(profile('Trap',['Pop Rap']),profile('Trap',['Pop Rap']))
 def test_40_all_strengths_bounded(self):
    for c in CONFIG['concepts']:
      for v in profile(c['label'])['neighborhood_memberships'].values():self.assertTrue(0<=v<=1)
if __name__=='__main__':unittest.main(verbosity=2)
