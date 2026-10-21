import os
import tempfile
import unittest
from hypr_doctor.doctor import HyprDoctor

class TestHyprDoctor(unittest.TestCase):
    def test_clean_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            conf = os.path.join(tmpdir, "hyprland.conf")
            with open(conf, "w") as f:
                f.write("""
$mainMod = SUPER
bind = $mainMod, Return, exec, alacritty
bind = $mainMod, Q, killactive
bind = $mainMod, Space, exec, rofi -show drun
""")
            doc = HyprDoctor(conf)
            res = doc.audit()
            self.assertEqual(res["summary"]["critical"], 0)
            self.assertEqual(res["total_binds"], 3)
            self.assertTrue(res["summary"]["clean"])

    def test_duplicate_bind_detection(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            conf = os.path.join(tmpdir, "hyprland.conf")
            with open(conf, "w") as f:
                f.write("""
$mainMod = SUPER
bind = $mainMod ALT, M, exec, iram-models
bind = $mainMod ALT, M, exec, iram-music
""")
            doc = HyprDoctor(conf)
            res = doc.audit()
            self.assertEqual(res["summary"]["critical"], 1)
            self.assertEqual(res["issues"][0]["type"], "DUPLICATE_BIND")
            self.assertIn("Conflicting keybind", res["issues"][0]["message"])

    def test_submap_isolation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            conf = os.path.join(tmpdir, "hyprland.conf")
            with open(conf, "w") as f:
                f.write("""
bind = , escape, exec, echo "global escape"
submap = resize
bind = , escape, submap, reset
submap = reset
""")
            doc = HyprDoctor(conf)
            res = doc.audit()
            # Escape in global and escape in resize submap must NOT collide
            self.assertEqual(res["summary"]["critical"], 0)

    def test_fix_duplicate_comment_strategy(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            conf = os.path.join(tmpdir, "hyprland.conf")
            with open(conf, "w") as f:
                f.write("""$mainMod = SUPER
bind = $mainMod, Return, exec, alacritty
bind = $mainMod, Return, exec, kitty
""")
            doc = HyprDoctor(conf)
            fix_res = doc.fix(strategy="comment")
            self.assertEqual(fix_res["fixed_count"], 1)
            self.assertEqual(len(fix_res["backups"]), 1)
            self.assertTrue(os.path.exists(fix_res["backups"][0]))

            # Re-audit must now be clean
            audit_after = doc.audit()
            self.assertEqual(audit_after["summary"]["critical"], 0)
            self.assertTrue(audit_after["summary"]["clean"])

            with open(conf, "r") as f:
                content = f.read()
            self.assertIn("# [hypr-doctor disabled duplicate of line 2]", content)

    def test_fix_duplicate_remap_strategy(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            conf = os.path.join(tmpdir, "hyprland.conf")
            with open(conf, "w") as f:
                f.write("""$mainMod = SUPER
bind = $mainMod, O, exec, iram-orchestrator
bind = $mainMod, O, exec, obsidian
""")
            doc = HyprDoctor(conf)
            fix_res = doc.fix(strategy="remap")
            self.assertEqual(fix_res["fixed_count"], 1)

            # Re-audit must be clean
            audit_after = doc.audit()
            self.assertEqual(audit_after["summary"]["critical"], 0)

            with open(conf, "r") as f:
                content = f.read()
            self.assertIn("bind = $mainMod CTRL ALT, O, exec, obsidian", content)

    def test_fix_clean_config_noop(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            conf = os.path.join(tmpdir, "hyprland.conf")
            with open(conf, "w") as f:
                f.write("""$mainMod = SUPER\nbind = $mainMod, Q, killactive\n""")
            doc = HyprDoctor(conf)
            fix_res = doc.fix()
            self.assertEqual(fix_res["fixed_count"], 0)
            self.assertEqual(len(fix_res["backups"]), 0)

if __name__ == "__main__":
    unittest.main()
