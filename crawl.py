#!/usr/bin/python2
# -*- coding:utf-8 -*-
# Created Time: Tue Oct  4 20:32:12 2016
# Mail: hewr2010@gmail.com
import re
import time
import json
import hashlib
import traceback
import urlparse
import requests
from bs4 import BeautifulSoup
from collections import OrderedDict

import argparse
parser = argparse.ArgumentParser()
parser.add_argument("--log", default="INFO", type=str, help="logging level")
parser.add_argument("--no_web_cache", action="store_true",
                    help="use cache for web page")
args = parser.parse_args()

import os
def safe_makedirs(path):
    if not os.path.exists(path):
        os.makedirs(path)

BASE_DIR = os.path.dirname(os.path.realpath(__file__))
CACHE_DIR = os.path.join(BASE_DIR, ".cache")
safe_makedirs(CACHE_DIR)
DATA_DIR = os.path.join(BASE_DIR, "data")
safe_makedirs(DATA_DIR)

import logging
logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(getattr(logging, args.log.upper()))
logger.addHandler(logging.FileHandler("log.txt"))
logging.addLevelName(logging.WARNING, "\033[1;31m%s\033[1;0m" % logging.getLevelName(logging.WARNING))
logging.addLevelName(logging.ERROR, "\033[1;41m%s\033[1;0m" % logging.getLevelName(logging.ERROR))

GLOBAL_SETTINGS = {
    "url": "",
    "city": "",
    "date": "",
    "house": "",
    "type": "",
    "developer": "",
    "PM": "",
    "area": "",
    "PM_fee": "",
}


ERROR_URLS_FILENAME = "error_urls.txt"
def mark_error_url(url):
    logger.error("style not recognize %s" % url)
    fout = open(ERROR_URLS_FILENAME, "a")
    fout.write("%s\n" % url)
    fout.close()


WARN_URLS_FILENAME = "warn_urls.txt"
def mark_warn_url(url):
    logger.warn("may have a problem %s" % url)
    fout = open(WARN_URLS_FILENAME, "a")
    fout.write("%s\n" % url)
    fout.close()


def get_top_cities():
    return [u"北京", u"深圳", u"广州"]

def get_strong_second_line_cities():
    return [
        u"天津", u"宁波", u"杭州", u"成都", u"重庆", u"西安",
        u"沈阳", u"大连", u"青岛", u"无锡", u"苏州", u"南京",
        u"武汉", u"长沙", u"厦门",
    ]

def get_second_line_cities():
    return [
        u"郑州", u"南宁", u"汕头", u"海口", u"昆明", u"贵阳",
        u"长春", u"哈尔滨", u"济南", u"烟台", u"太原", u"南通",
        u"常州", u"扬州", u"徐州", u"合肥", u"福州", u"南昌",
    ]

def get_city_list():
    return get_top_cities() +\
        get_strong_second_line_cities() +\
        get_second_line_cities()


browser = requests.Session()
headers = {
    "User-Agent": "Mozilla/5.0",
    "Content-Type": "application/x-www-form-urlencoded"
}

def get_page(url, sleep_time=0.5, timeout_secs=10,
             use_cache=not args.no_web_cache):
    cache_filename = os.path.join(CACHE_DIR,
                                  "%s.json" % hashlib.md5(url).hexdigest())
    logger.info("visit %s" % url)
    if os.path.isfile(cache_filename) and use_cache:
        logger.info("load from file %s" % cache_filename)
        return json.load(open(cache_filename))["content"]
    else:
        while True:
            try:
                obj = browser.get(url, timeout=timeout_secs)
                break
            except requests.exceptions.ReadTimeout:
                pass
        #obj.encoding = obj.apparent_encoding
        obj.encoding = "GB2312"  # XXX hard code for this weird website
        time.sleep(sleep_time)
        json.dump({"url": url, "content": obj.text}, open(cache_filename, "w"))
        return obj.text


def process_house_info(url):
    def process_style1(soup):
        info = GLOBAL_SETTINGS.copy()
        try:
            panel_lst = soup.find("div", {"class": "main-cont"})\
                .find("div", {"class": "main-left"})\
                .find_all("div", {"class": "main-item"})
        except AttributeError as e:
            raise e
        KEY_MAP = {
            u"物业类别": "type",
            u"开发商": "developer",
            u"建筑面积": "area",
            u"物业公司": "PM",
            u"物业费": "PM_fee",
        }
        for panel in panel_lst:
            panel_title = panel.find("h3").text.strip()
            if panel_title in [u"基本信息", u"小区规划"]:
                for kv_block in panel.find_all("li"):
                    key = kv_block.find("div", {"class": "list-left"}).text\
                        .strip()
                    key = re.sub(' ', '', key)  # thanks to the ugly frontend
                    for trg_key in KEY_MAP:
                        if trg_key == key[:len(trg_key)]:
                            info[KEY_MAP[trg_key]] = kv_block.find_next("div")\
                                .find_next("div").text.strip()
        return info

    def process_style2(soup):
        info = GLOBAL_SETTINGS.copy()
        try:
            panel = soup.find("div", {"class": "besic_inform"})
        except AttributeError as e:
            raise e
        for td in panel.find_all("td"):
            if td.find("strong") is not None:
                key = td.find("strong").text
                value = td.text[len(key):].strip()
                if key.find(u"商铺类型") == 0 or key.find(u"写字楼类型") == 0:
                    info["type"] = value
                elif key.find(u"建筑面积") == 0:
                    info["area"] = value
                elif key.find(u"物业管理费") == 0:
                    info["PM_fee"] = value
        # find developer
        block = soup.find("div", {"class": "besic_inform"})\
            .find_all("div", {"class": "lineheight"})[-1]
        info["developer"] = ""
        for item in block.find_all("strong"):
            if item.text.find(u"开发商") == 0:
                value = item.find_next().text
                info["developer"] = value.strip()
        info["PM"] = ""  # XXX no PM
        return info

    def process_styles(soup):
        def strip_value_developer(s):
            tmpl = u"[房企申请入驻]"
            if s[-len(tmpl):] == tmpl:
                s = s[:-len(tmpl)]
            return s

        _logs = []
        for style in range(1, 3):
            try:
                if style == 1:
                    info = process_style1(soup)
                elif style == 2:
                    info = process_style2(soup)
            except AttributeError:
                _logs.append(traceback.format_exc())
                continue
            info["developer"] = strip_value_developer(info["developer"])
            return (info, style)
        for _log in _logs:
            logger.debug(_log)
        return (None, -1)

    # parse info
    GLOBAL_SETTINGS["url"] = url
    soup = BeautifulSoup(get_page(url))
    info, style = process_styles(soup)
    if info is None:
        mark_error_url(url)
        return
    # verify info
    logger.info("house details page style [%d]" % style)
    logger.info(json.dumps(info, ensure_ascii=False, indent=4))
    info_quality_pass = True
    for k, v in info.items():
        if len(v) == 0 and (k != "PM" or style != 2):
            logger.warn("probably miss information [%s]" % k)
            info_quality_pass = False
    if not info_quality_pass:
        mark_warn_url(url)
    # save info
    filename = os.path.join(
        DATA_DIR, GLOBAL_SETTINGS["city"], GLOBAL_SETTINGS["date"],
        "%s.json" % GLOBAL_SETTINGS["house"],
    )
    safe_makedirs(os.path.dirname(filename))
    json.dump(info, open(filename, "w"))


def process_house(url):
    soup = BeautifulSoup(get_page(url))
    for obj in soup.find_all("a"):
        if obj.text.find(u"详细信息>>") != -1:
            process_house_info(urlparse.urljoin(url, obj["href"]))
            break


def process_city(url):
    def get_house_url(url):
        idx = url.find(":")
        if url[idx + 3:idx + 6] == "bj.":
            # special case for beijing
            prefix = "http://newhouse.fang.com"
        else:
            prefix = url[:idx + 3] + "newhouse." + url[idx + 3:]
        return urlparse.urljoin(prefix, "house/saledate/201601.htm")

    def get_housing_date_url(url, month):
        arr = url.split(".")
        return ".".join(arr[:-1])[:-2] + "%02d" % month + "." + arr[-1]

    def process_page(url):
        soup = BeautifulSoup(get_page(url))
        list_area = soup.find("div", {"class": "listArea"})
        for obj in list_area.find_all("li"):
            trg_a = obj.find("div", {"class": "text"})\
                .find("a", {"class": "floatl w130"})
            trg_name = trg_a.text
            logger.info("house %s" % trg_name)
            GLOBAL_SETTINGS["house"] = trg_name
            trg_url = urlparse.urljoin(url, trg_a["href"])
            process_house(trg_url)

    def get_next_page_url(url):
        soup = BeautifulSoup(get_page(url))
        page_div = soup.find("div", {"class": "page"})
        lst = page_div.find_all("a")
        if len(lst) > 2:
            obj = lst[-2]
            if obj.text != u"下一页":
                return None
            else:
                return urlparse.urljoin(url, obj["href"])
        else:
            return None

    base_url = get_house_url(url)
    for month in range(1, 10):
        logger.info("month %d" % month)
        GLOBAL_SETTINGS["date"] = "2016%02d" % month
        page_url = get_housing_date_url(base_url, month)
        page_num = 0
        while page_url is not None:
            page_num += 1
            logger.info("page %d" % page_num)
            process_page(page_url)
            page_url = get_next_page_url(page_url)


def process_cities(cities):
    urls = []
    soup = BeautifulSoup(get_page("http://fang.com/SoufunFamily.htm"))
    for item in soup.find_all('a'):
        if item.text in cities:
            urls.append((item.text, item["href"]))
    urls = OrderedDict(urls)
    for city, url in urls.items():
        logger.info("city %s" % city)
        GLOBAL_SETTINGS["city"] = city
        process_city(url)


if __name__ == "__main__":
    os.system("rm -rf %s %s %s" % (
        ERROR_URLS_FILENAME, WARN_URLS_FILENAME, DATA_DIR))
    process_cities(get_city_list())

