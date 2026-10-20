import copy
import unittest
from datetime import datetime, timedelta
import update_calendar as u

class Safeguards(unittest.TestCase):
    def row(self,name='UConn',opponent='Texas',gid='100',start='2026-11-05T19:00:00'):
        src=next(s for s in u.SOURCES if s['name']==name)
        return u.game(src,gid,opponent,start,False,'Arena','ESPN2',[])
    def test_duplicate_and_alias(self):
        a=self.row(opponent='Southern Cal');b=self.row('USC','Connecticut','200','2026-11-05T16:00:00')
        r=u.reconcile([b,a],{});self.assertEqual(len(r['games']),1)
    def test_dst(self):
        a=self.row(start='2026-10-30T19:00:00');b=self.row(start='2026-11-05T19:00:00')
        self.assertEqual(u.iso(a['start']).astimezone(u.PACIFIC).hour,16)
        self.assertEqual(u.iso(b['start']).astimezone(u.PACIFIC).hour,16)
    def test_conflicting_official_tipoff_fails(self):
        with self.assertRaises(ValueError):u.reconcile([self.row(),self.row('Texas','UConn','200','2026-11-05T19:00:00')],{})
    def test_reschedule_preserves_uid_and_requires_confirmation(self):
        old=u.reconcile([self.row()],{});uid=next(iter(old['games']))
        change=self.row(start='2026-11-06T19:00:00');pending=u.reconcile([change],old)
        self.assertEqual(pending['games'][uid]['date'],'2026-11-05')
        pending['pending'][uid]['first_seen']=(u.NOW-timedelta(hours=1)).isoformat()
        accepted=u.reconcile([change],pending)
        self.assertEqual(accepted['games'][uid]['date'],'2026-11-06')
        self.assertEqual(accepted['games'][uid]['sequence'],1)
    def test_disappeared_game_is_retained(self):
        old=u.reconcile([self.row()],{});r=u.reconcile([],old)
        self.assertEqual(r['games'],old['games'])
    def test_no_unconfirmed_tournament_games(self):
        self.assertFalse(u.reconcile([self.row(opponent='NCAA Tournament')],{})['games'])
    def test_input_order_does_not_change_feed(self):
        a=self.row();b=self.row('Texas','UConn','200','2026-11-05T18:00:00')
        self.assertEqual(u.reconcile([a,b],{}),u.reconcile([b,a],{}))
    def test_tba_does_not_invent_tipoff(self):
        src=u.SOURCES[0];r=u.game(src,'x','Texas','2026-11-05T00:00:00',True,'Arena')
        self.assertIsNone(r['start'])
    def test_services(self):
        self.assertIn('included',u.service('ACCNX / SECN+ / ESPN+'))
        self.assertIn('separate paid',u.service('B1G+'))
        self.assertNotIn('Paramount+ — included',u.service('CBS Sports Network'))

if __name__=='__main__':unittest.main()
