import unittest
from unittest.mock import Mock
from layout import button_size, default_positions, load_layouts, place_button
from lcu import ClientError, selected_players


class LayoutChecks(unittest.TestCase):
    def test_normal_window(self):
        self.assertEqual(place_button((100, 100, 1280, 720), (.17, .19), (122, 34),
                                      [(0, 0, 1920, 1040)]), (318, 237, 122, 34))

    def test_partial_left_edge_is_clamped(self):
        self.assertEqual(place_button((-280, 100, 1280, 720), (.17, .19), (122, 34),
                                      [(0, 0, 1920, 1040)]), (0, 237, 122, 34))

    def test_offscreen_floor_hidden_instead_of_piled_up(self):
        self.assertIsNone(place_button((-500, 100, 1280, 720), (.17, .19), (122, 34),
                                       [(0, 0, 1920, 1040)]))

    def test_above_screen_and_bottom_edge(self):
        screens = [(0, 0, 1920, 1040)]
        self.assertIsNone(place_button((100, -500, 1280, 720), (.17, .19), (122, 34), screens))
        self.assertEqual(place_button((100, 850, 1280, 720), (.17, .24), (122, 34), screens), (318, 1006, 122, 34))

    def test_negative_monitor_coordinates_are_valid(self):
        screens = [(-1920, -200, 0, 880), (0, 0, 1920, 1040)]
        self.assertEqual(place_button((-1700, -100, 1280, 720), (.17, .19), (122, 34), screens),
                         (-1482, 37, 122, 34))

    def test_monitor_gap_is_not_visible_desktop(self):
        screens = [(-1920, 0, 0, 1040), (300, 0, 2220, 1040)]
        self.assertIsNone(place_button((-100, 100, 1280, 720), (.17, .19), (122, 34), screens))

    def test_spanning_monitor_seam_keeps_whole_button_on_one_display(self):
        screens = [(0, 0, 1920, 1040), (1920, 0, 3840, 1040)]
        result = place_button((1700, 100, 1280, 720), (.17, .19), (122, 34), screens)
        self.assertEqual(result, (1920, 237, 122, 34))

    def test_too_little_visible_client_space_hides_button(self):
        self.assertIsNone(place_button((1880, 100, 1280, 720), (0, .19), (122, 34), [(0, 0, 1920, 1040)]))

    def test_small_and_large_teams(self):
        for count in (0, 1, 3, 5, 6, 8, 10, 16, 20):
            team = selected_players({'myTeam': [{'cellId': i, 'championId': 22} for i in range(count)]})
            self.assertEqual([p['floor'] for p in team], list(range(1, count+1)))

    def test_vacant_floors_do_not_change_other_floor_numbers(self):
        team = selected_players({'myTeam': [{'cellId': 1}, {'cellId': 3}]})
        self.assertEqual([p['floor'] for p in team], [2, 4])
        team = selected_players({'myTeam': [{'cellId': 5}, {'cellId': 7}]})
        self.assertEqual([p['floor'] for p in team], [1, 3])

    def test_bad_or_duplicate_slots_fail_closed(self):
        for cells in ([1, 1], [-1], [None], ['2']):
            with self.assertRaises(ClientError):
                selected_players({'myTeam': [{'cellId': i} for i in cells]})

    def test_legacy_calibration_and_separate_layouts(self):
        old = default_positions(5)
        old[1] = [.33, .4]
        self.assertEqual(load_layouts(old), {'5': old})
        value = {'version': 2, 'layouts': {'5': old, '8': default_positions(8)}}
        self.assertEqual(load_layouts(value), value['layouts'])
        self.assertEqual(load_layouts({'version': 2, 'layouts': []}), {})
        self.assertEqual(load_layouts({'version': 2, 'layouts': {'5': [[float('nan'), 0]]*5}}), {})

    def test_ten_buttons_fit_small_client_without_vertical_overlap(self):
        positions = default_positions(10)
        bw, bh = button_size(720, 400, 10)
        rows = [place_button((0, 0, 720, 400), p, (bw, bh), [(0, 0, 1920, 1040)]) for p in positions]
        self.assertTrue(all(rows))
        self.assertTrue(all(a[1]+a[3] <= b[1] for a, b in zip(rows, rows[1:])))

    def test_live_widget_count_changes_and_clicks_target_current_rows(self):
        import tkinter as tk
        from overlay import Overlay, monitor_workareas
        root = tk.Tk()
        root.withdraw()
        try:
            panel = Overlay.__new__(Overlay)
            panel.root, panel.buttons = root, []
            panel.layouts, panel.layout_slots = {'5': default_positions(5)}, 5
            panel.positions = panel.layouts['5']
            panel.drag = None
            panel.send = Mock()
            for count in (3, 8, 2, 0, 10):
                panel.players = selected_players({'myTeam': [{'cellId': i} for i in range(count)]})
                panel.sync_buttons()
                root.update_idletasks()
                self.assertEqual(len(panel.buttons), count)
                for i, (win, btn) in enumerate(panel.buttons):
                    self.assertEqual(win.state(), 'withdrawn')
                    btn.invoke()
                    panel.send.assert_called_with(i)
            self.assertTrue(monitor_workareas())
        finally:
            root.destroy()


if __name__ == '__main__':
    unittest.main()
