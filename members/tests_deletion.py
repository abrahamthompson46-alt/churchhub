"""Regression tests for P0-10 guarded hard deletes."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserRole
from members.models import Department, Member, MemberAuditLog, MemberSpiritualGift, SpiritualGift
from members.services import MemberServiceError, delete_department, unassign_spiritual_gift
from organization.models import Church, Conference, District, Zone
from transactions.models import Account, Budget, FinancialAuditLog
from transactions.services import approve_transaction, record_receipt

User = get_user_model()


class DepartmentDeleteGuardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        conf = Conference.objects.create(name="Del Conf", code="DELC")
        zone = Zone.objects.create(conference=conf, name="Del Z", code="DELZ")
        dist = District.objects.create(zone=zone, name="Del D", code="DELD")
        cls.church = Church.objects.create(district=dist, name="Del Church", code="DELCH")
        cls.user = User.objects.create_user(
            username="del_secretary",
            password="pass12345",
            role=UserRole.SECRETARY,
            church=cls.church,
        )

    def test_delete_unused_department_audited(self):
        dept = Department.objects.create(church=self.church, name="Empty Dept")
        delete_department(dept, self.user)
        self.assertFalse(Department.objects.filter(pk=dept.pk).exists())
        self.assertTrue(
            MemberAuditLog.objects.filter(
                church=self.church,
                action="DEPARTMENT_DELETE",
            ).exists()
        )

    def test_delete_blocked_when_members_assigned(self):
        dept = Department.objects.create(church=self.church, name="Youth")
        Member.objects.create(
            church=self.church,
            department=dept,
            first_name="A",
            last_name="Member",
            gender="Male",
        )
        with self.assertRaises(MemberServiceError):
            delete_department(dept, self.user)
        self.assertTrue(Department.objects.filter(pk=dept.pk).exists())

    def test_department_delete_view_blocks_with_members(self):
        dept = Department.objects.create(church=self.church, name="Choir")
        Member.objects.create(
            church=self.church,
            department=dept,
            first_name="B",
            last_name="Singer",
            gender="Female",
        )
        client = Client()
        client.login(username="del_secretary", password="pass12345")
        response = client.post(reverse("members:department_delete", kwargs={"pk": dept.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Department.objects.filter(pk=dept.pk).exists())


class SpiritualGiftUnassignAuditTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        conf = Conference.objects.create(name="Gift Conf", code="GIFC")
        zone = Zone.objects.create(conference=conf, name="Gift Z", code="GIFZ")
        dist = District.objects.create(zone=zone, name="Gift D", code="GIFD")
        cls.church = Church.objects.create(district=dist, name="Gift Church", code="GIFCH")
        cls.member = Member.objects.create(
            church=cls.church,
            first_name="Gift",
            last_name="Bearer",
            gender="Male",
        )
        cls.gift = SpiritualGift.objects.create(church=cls.church, name="Teaching")
        cls.user = User.objects.create_user(
            username="gift_secretary",
            password="pass12345",
            role=UserRole.SECRETARY,
            church=cls.church,
        )

    def test_unassign_writes_member_audit(self):
        assignment = MemberSpiritualGift.objects.create(member=self.member, gift=self.gift)
        unassign_spiritual_gift(assignment, self.user)
        self.assertFalse(MemberSpiritualGift.objects.filter(pk=assignment.pk).exists())
        self.assertTrue(
            MemberAuditLog.objects.filter(
                member=self.member,
                action="GIFT_UNASSIGN",
            ).exists()
        )


class BudgetDeleteGuardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        conf = Conference.objects.create(name="Bud Conf", code="BUDC")
        zone = Zone.objects.create(conference=conf, name="Bud Z", code="BUDZ")
        dist = District.objects.create(zone=zone, name="Bud D", code="BUDD")
        cls.church = Church.objects.create(district=dist, name="Bud Church", code="BUDCH")
        cls.income = Account.objects.get(church=cls.church, name="General Income")
        cls.user = User.objects.create_user(
            username="bud_treasury",
            password="pass12345",
            role=UserRole.TREASURY,
            church=cls.church,
        )
        from transactions.services import open_working_day

        open_working_day(cls.church, timezone.localdate(), cls.user)

    def test_delete_blocked_when_actuals_exist(self):
        from budgets.services import BudgetServiceError, delete_budget

        if not self.income:
            self.skipTest("General Income account not seeded")

        budget = Budget.objects.create(
            church=self.church,
            level="CHURCH",
            year=timezone.now().year,
            account=self.income,
            amount=Decimal("1000.00"),
        )
        pastor = User.objects.create_user(
            username="del_pastor",
            password="pass12345",
            role=UserRole.LOCAL_PASTOR,
            church=self.church,
        )
        txn = record_receipt(
            self.church,
            self.user,
            income_amount=Decimal("50.00"),
            description="Offering",
        )
        approve_transaction(txn, pastor)
        with self.assertRaises(BudgetServiceError):
            delete_budget(budget, self.user, self.church)
        self.assertTrue(Budget.objects.filter(pk=budget.pk).exists())
        self.assertFalse(
            FinancialAuditLog.objects.filter(action="BUDGET_DELETE", church=self.church).exists()
        )
