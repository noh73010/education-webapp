from django.core.management.base import BaseCommand
from core.services.concept_catalog import sync_guided_concepts

class Command(BaseCommand):
    help='Link only the inspected versions of curated concept questions.'
    def handle(self,*args,**kwargs):
        linked,held=sync_guided_concepts()
        self.stdout.write(f'Guided concepts: linked={linked}, changed_or_unavailable={held}')
