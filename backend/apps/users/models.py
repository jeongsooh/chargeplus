from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Extended user model for ChargePlus service users."""

    class Role(models.TextChoices):
        CS       = 'cs',       '고객센터'
        PARTNER  = 'partner',  '파트너'
        CUSTOMER = 'customer', '고객'

    class PortalStatus(models.TextChoices):
        PENDING  = 'pending',  '승인대기'
        ACTIVE   = 'active',   '활성'
        INACTIVE = 'inactive', '비활성'

    phone      = models.CharField(max_length=20, blank=True)
    role       = models.CharField(max_length=10, choices=Role.choices, default=Role.CUSTOMER)
    status     = models.CharField(max_length=10, choices=PortalStatus.choices, default=PortalStatus.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'cp_user'
        verbose_name = 'User'
        verbose_name_plural = 'Users'

    def __str__(self):
        return f"{self.username} ({self.get_full_name() or self.email})"

    @property
    def is_portal_active(self):
        return self.status == self.PortalStatus.ACTIVE


class PartnerProfile(models.Model):
    """Business profile for partner-role users."""
    user          = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='partner_profile',
        limit_choices_to={'role': User.Role.PARTNER},
    )
    business_name  = models.CharField(max_length=100, verbose_name='사업체명')
    business_no    = models.CharField(max_length=20, verbose_name='사업자번호')
    contact_phone  = models.CharField(max_length=20, blank=True, verbose_name='담당자 연락처')
    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'cp_partner_profile'
        verbose_name = 'Partner Profile'
        verbose_name_plural = 'Partner Profiles'

    def __str__(self):
        return f"{self.business_name} ({self.user.username})"
