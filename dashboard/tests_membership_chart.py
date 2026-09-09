"""Active-member comparison chart — church / district / conference, scoped ids only."""

from django.test import TestCase
from django.utils import timezone

from dashboard.home_panels import get_membership_analysis
from members.models import Gender, MembershipStatus, Member
from organization.models import Church, Conference, District, Zone
from sitecontrol.models import Denomination


class MembershipComparisonChartTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.denomination = Denomination.objects.create(
            code="mchart", name="Chart Denom", is_active=True
        )
        cls.conf_a = Conference.objects.create(
            code="CA", name="Conference Alpha", denomination=cls.denomination
        )
        cls.conf_b = Conference.objects.create(
            code="CB", name="Conference Beta", denomination=cls.denomination
        )
        zone_a = Zone.objects.create(conference=cls.conf_a, code="ZA", name="Zone A")
        zone_b = Zone.objects.create(conference=cls.conf_b, code="ZB", name="Zone B")
        cls.dist_a = District.objects.create(zone=zone_a, code="DA", name="District A")
        cls.dist_d = District.objects.create(zone=zone_a, code="DD", name="District D")
        cls.dist_f = District.objects.create(zone=zone_b, code="DF", name="District F")
        cls.church_a = Church.objects.create(district=cls.dist_a, code="A", name="Church A")
        cls.church_d = Church.objects.create(district=cls.dist_d, code="D", name="Church D")
        cls.church_f = Church.objects.create(district=cls.dist_f, code="F", name="Church F")
        cls.church_g = Church.objects.create(district=cls.dist_f, code="G", name="Church G")
        cls.outsider = Church.objects.create(district=cls.dist_a, code="X", name="Outsider")

        def _member(church, name, status=MembershipStatus.ACTIVE):
            Member.objects.create(
                church=church,
                first_name=name,
                last_name="Member",
                gender=Gender.FEMALE,
                membership_status=status,
            )

        for _ in range(5):
            _member(cls.church_a, "Ada")
        for _ in range(3):
            _member(cls.church_d, "Dan")
        for _ in range(2):
            _member(cls.church_f, "Fay")
        _member(cls.church_g, "Gia")
        _member(cls.church_a, "Inactive", MembershipStatus.INACTIVE)
        _member(cls.outsider, "Eve")

    def test_counts_active_status_and_groups_hierarchy(self):
        scoped = [self.church_a.id, self.church_d.id, self.church_f.id, self.church_g.id]
        snap = get_membership_analysis(scoped, timezone.localdate().replace(day=1))
        self.assertIsNotNone(snap)
        self.assertEqual(snap["totals"]["members"], 11)
        labels = [p["label"] for p in snap["chart"]["churches"]]
        self.assertEqual(labels[0], "Church A")
        self.assertNotIn("Outsider", labels)
        by_church = {p["label"]: p["value"] for p in snap["chart"]["churches"]}
        self.assertEqual(by_church["Church A"], 5)
        self.assertEqual(by_church["Church D"], 3)
        self.assertIn("district", snap["chart"]["levels"])
        self.assertIn("conference", snap["chart"]["levels"])
        districts = {p["label"]: p["value"] for p in snap["chart"]["districts"]}
        self.assertEqual(districts["District A"], 5)
        self.assertEqual(districts["District F"], 3)
        conferences = {p["label"]: p["value"] for p in snap["chart"]["conferences"]}
        self.assertEqual(conferences["Conference Alpha"], 8)
        self.assertEqual(conferences["Conference Beta"], 3)

    def test_does_not_include_churches_outside_passed_ids(self):
        snap = get_membership_analysis(
            [self.church_a.id], timezone.localdate().replace(day=1)
        )
        labels = [p["label"] for p in snap["chart"]["churches"]]
        self.assertEqual(labels, ["Church A"])
        self.assertNotIn("conference", snap["chart"]["levels"])
