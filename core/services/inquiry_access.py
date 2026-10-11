from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount
from django.conf import settings


def is_inquiry_owner(user):
    owner_email = settings.INQUIRY_OWNER_EMAIL
    return bool(
        owner_email
        and user.is_authenticated
        and user.is_active
        and EmailAddress.objects.filter(user=user, email__iexact=owner_email, verified=True).exists()
        and SocialAccount.objects.filter(user=user, provider="google").exists()
    )
