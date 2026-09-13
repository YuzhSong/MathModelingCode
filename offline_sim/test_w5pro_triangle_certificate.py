from __future__ import annotations

import unittest

from q3.models import Point
from q4.w5pro_triangle_certificate import (
    ChannelTriangleCertificate,
    enumerate_legal_triangles,
    frozen_w5_certificate,
    select_certificate_mesh,
    verify_bounded_cells,
    verify_continuous_mesh,
)


class TriangleCertificateTests(unittest.TestCase):
    def test_frozen_w5_has_explicit_legal_topology(self):
        points, triangles = frozen_w5_certificate()
        self.assertEqual(len(points), 25)
        self.assertGreater(len(triangles), 0)
        self.assertTrue(all(len(set(t.vertices)) == 3 for t in triangles))

    def test_delaunay_certificate_mesh_is_selected_from_legal_faces(self):
        points, _ = frozen_w5_certificate()
        mesh = select_certificate_mesh(points)
        self.assertGreater(len(mesh), 0)
        self.assertTrue(all(len(set(t.vertices)) == 3 for t in mesh))

    def test_mesh_audit_covers_disk_at_test_resolution(self):
        points, triangles = frozen_w5_certificate()
        audit = verify_continuous_mesh(points, triangles, spacing_m=100.0)
        self.assertEqual(audit["uncovered_samples"], 0)
        self.assertEqual(audit["continuous_audit_pass"], 1)

    def test_bounded_cell_audit_never_promotes_unresolved_cells(self):
        points, triangles = frozen_w5_certificate()
        audit = verify_bounded_cells(points, triangles, cell_size_m=20.0)
        self.assertGreater(audit["cells"], 0)
        self.assertEqual(audit["bounded_cell_pass"],
                         int(audit["unresolved_cells"] == 0))

    def test_triangle_requires_three_no_signal_vertices(self):
        triangles = enumerate_legal_triangles([Point(0, 0), Point(500, 0), Point(0, 500)])
        cert = ChannelTriangleCertificate(triangles)
        t = triangles[0]
        cert.observe(7, t.vertices[0], "no_signal")
        cert.observe(7, t.vertices[1], "no_signal")
        self.assertFalse(cert.hard_complete(7))
        cert.observe(7, t.vertices[2], "no_signal")
        self.assertTrue(cert.hard_complete(7))

    def test_positive_observation_prevents_absence_certificate(self):
        points, triangles = frozen_w5_certificate()
        cert = ChannelTriangleCertificate(triangles)
        cert.observe(3, triangles[0].vertices[0], "direction")
        for vertex in triangles[0].vertices:
            cert.observe(3, vertex, "no_signal")
        self.assertIn(3, cert.present_channels)
        self.assertFalse(cert.hard_complete(3))


if __name__ == "__main__":
    unittest.main()
