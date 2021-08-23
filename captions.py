#!/usr/bin/env python3
"""Sample wiki pages and analyze image captions."""

import argparse
import sys

from bs4 import (
    BeautifulSoup as Soup,
    Tag
)
import csv
import json
from pprint import PrettyPrinter
import requests
import soupsieve
import sys
import urllib
from typing import List, Optional


def get_random_articles(lang: str, count: int = 100) -> List[str]:
    api_url = f"https://{lang}.wikipedia.org/w/api.php"
    r = requests.get(api_url, params={
        "format": "json",
        "formatversion": 2,
        "action": "query",
        "list": "random",
        "rnnamespace": 0,
        "rnfilterredir": "nonredirects",
        "rnlimit": count,
    })
    data = r.json()
    titles = []
    for item in data["query"]["random"]:
        titles.append(item["title"])
    return titles


def get_parsoid_html(lang: str, title: str) -> str:
    title = urllib.parse.quote(title.replace(' ', '_'), safe='')
    parsoid_url = f"https://{lang}.wikipedia.org/api/rest_v1/page/html/{title}"
    r = requests.get(parsoid_url)
    return r.text


def get_attrib(tag: Tag, selector: Optional[str], attrib: str) -> Optional[str]:
    if selector:
        tag = tag.select_one(selector)
    if tag:
        return tag.attrs.get(attrib)
    return None


def remove_dot(str: Optional[str]) -> Optional[str]:
    """Remove leading ./ from Parsoid titles"""
    if str:
        str = str[2:]
    return str


def get_image_data_from_html(html: str, page: str) -> List[dict]:
    soup = Soup(html, "lxml")
    data = []
    for tag in soup.select('[typeof="mw:Image"],[typeof^="mw:Image/"]'):
        # see https://www.mediawiki.org/wiki/Specs/HTML/2.2.0#Media

        item_data = {
            "filename": remove_dot(get_attrib(tag, "img", "resource")),
            "position": "block" if tag.name == "figure" else "inline",
            "type": tag.attrs["typeof"][len("mw:Image/"):].lower() or "image",  # image/thumb/frame/frameless
            "width": get_attrib(tag, "img", "width"),
            "height": get_attrib(tag, "img", "height"),
            "orig-width": get_attrib(tag, "img", "data-file-width"),
            "orig-height": get_attrib(tag, "img", "data-file-height"),
            "mediatype": get_attrib(tag, "img", "data-file-type"),  # lowercased MEDIATYPE_* value, probably?
            "from_template": soupsieve.closest('[typeof="mw:Transclusion"], [about]', tag).name != "html",
        }

        caption = None
        if tag.name == "span":
            attribs = get_attrib(tag, None, "data-mw")
            if attribs:
                attribs = json.loads(attribs)
                if attribs["caption"]:
                     caption = attribs["caption"]
        elif tag.name == 'figure' or tag.name == 'figure-inline':
            figcaption = tag.select_one("figcaption")
            if figcaption and figcaption.string:
                caption = str(tag.select_one("figcaption").string)
        else:
            raise Exception(f"Unexpected tag: {tag.name} (page: {page})")
        if caption:
            item_data["caption"] = Soup(caption, "lxml").get_text().replace("\n", " ")

        alt = get_attrib(tag, "img", "alt")
        if alt != None:
            item_data["alt"] = alt

        link = remove_dot(get_attrib(tag, "a", "href"))
        if link != item_data["filename"]:
            item_data["link"] = link

        src = get_attrib(tag, "img", "src")
        item_data["from_commons"] = src.startswith("//upload.wikimedia.org/wikipedia/commons/")

        data.append(item_data)
    return data


def handle_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sample wiki pages and analyze image captions.")
    parser.add_argument("--lang", type=str, required=True, help="Wiki language code")
    parser.add_argument("--page", type=str, help="Page title")
    parser.add_argument("-n", type=int, default=100, help="Number of pages to sample")
    parser.add_argument("--ignore-templates", action="store_const", default=False, const=True, help="Ignore images coming from templates")
    parser.add_argument("--output", type=str, choices=["print", "csv", "csv-headless"], default="print", help="Output format")
    return parser.parse_args()


def output_print(data):
    pp = PrettyPrinter()
    for page, page_data in data.items():
        print(f"== {page} ==")
        pp.pprint(page_data)
        print("\n\n")


def output_csv(data, add_header : bool = True):
    fieldnames = ["page_title", "filename", "caption", "alt", "position", "type", "link", "width", "height",
                  "orig-width", "orig-height", "mediatype", "from_template", "from_commons"]
    writer = csv.DictWriter(sys.stdout, fieldnames)
    if add_header:
        writer.writerow({
            "page_title": "Page name",
            "filename": "Image name",
            "caption": "Caption",
            "alt": "Alt text",
            "position": "Inline/block",
            "type": "Image format",
            "link": "Link",
            "width": "Thumbnail width",
            "height": "Thumbnail height",
            "orig-width": "Original width",
            "orig-height": "Original height",
            "mediatype": "Media type",
            "from_template": "From template?",
            "from_commons": "From commons?",
        })
    for page, page_data in data.items():
        for image_data in page_data:
            image_data["page_title"] = page
            writer.writerow(image_data)


def main():
    args = handle_args()

    if args.page:
        pages = [ args.page ]
    else:
        pages = get_random_articles(args.lang, args.n)

    data = {}
    for page in pages:
        html = get_parsoid_html(args.lang, page)
        page_data = get_image_data_from_html(html, page)
        if args.ignore_templates:
            page_data = [item for item in page_data if not item["from_template"]]
        if page_data:
            data[page] = page_data

    if args.output == 'print':
        output_print(data)
    elif args.output == 'csv' or args.output == 'csv-headless':
        output_csv(data, args.output == 'csv')


main()