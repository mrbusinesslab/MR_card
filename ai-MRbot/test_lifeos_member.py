import hashlib
import tempfile
import unittest
from pathlib import Path
from provision_lifeos_member import generate

class MemberTests(unittest.TestCase):
    def test_private_independent_invite(self):
        with tempfile.TemporaryDirectory() as root:
            out=generate('aa',"O'Brien",Path(root)/'member')
            token=(out/'activation.txt').read_text().strip().split(' ',1)[1]
            sql=(out/'register-member.sql').read_text()
            self.assertNotIn(token,sql)
            self.assertIn(hashlib.sha256(token.encode()).hexdigest(),sql)
            self.assertIn("O''Brien",sql);self.assertIn(',NULL)',sql)
            self.assertEqual((out/'activation.txt').stat().st_mode&0o777,0o600)
            with self.assertRaises(FileExistsError):generate('aa','x',out)
    def test_shared_owner_resolved_only_in_customer(self):
        with tempfile.TemporaryDirectory() as root:
            out=generate('aa','member',Path(root)/'member','U'+'1'*32)
            sql=(out/'register-member.sql').read_text()
            self.assertIn("tenant_id='aa' AND line_user_id=",sql)
            self.assertIn('AND shared_owner IS NULL',sql)
            self.assertNotIn('UPDATE',sql)
    def test_invalid_owner_and_mr_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ValueError):generate('aa','x',Path(root)/'x','bad')
            with self.assertRaises(ValueError):generate('mr','x',Path(root)/'x')
if __name__=='__main__':unittest.main()
