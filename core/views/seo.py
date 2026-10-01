from django.http import HttpResponse
from django.urls import reverse
from django.utils.html import escape
from django.views.decorators.http import require_safe


PUBLIC_PAGES = ("landing", "service_info", "content_sources")


@require_safe
def robots_txt(request):
    sitemap_url = request.build_absolute_uri(reverse("sitemap_xml"))
    return HttpResponse(
        f"User-agent: *\nAllow: /\nSitemap: {sitemap_url}\n",
        content_type="text/plain; charset=utf-8",
    )


@require_safe
def sitemap_xml(request):
    urls = "".join(
        f"<url><loc>{escape(request.build_absolute_uri(reverse(name)))}</loc></url>"
        for name in PUBLIC_PAGES
    )
    return HttpResponse(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{urls}</urlset>",
        content_type="application/xml; charset=utf-8",
    )
