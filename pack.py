#!/usr/bin/python2
# -*- coding:utf-8 -*-
# Created Time: Wed Oct  5 15:51:32 2016
# Mail: hewr2010@gmail.com
import os
import glob
import json
import xlsxwriter
from collections import OrderedDict
from crawl import get_city_list

BASE_DIR = os.path.dirname(os.path.realpath(__file__))

UNIT_NAME_AREA = u"平方米"
UNIT_NAME_PMFEE = u"元/平方米・月"

KEY_MAP = OrderedDict([
    (u"日期", "date"),
    (u"楼盘名称", "house"),
    (u"类型", "type"),
    (u"开发商", "developer"),
    (u"物业管理公司", "PM"),
    (u"面积(%s)" % UNIT_NAME_AREA, "area"),
    (u"物业费(%s)" % UNIT_NAME_PMFEE, "PM_fee"),
    (u"原网页", "url"),
])


def visual_length(s):
    ret = 0
    for c in s:
        _l = len(c.encode("utf8"))
        ret += 1 + int(_l > 1)
    return ret


def strip_unit_name(value, unit_name):
    if value[-len(unit_name):] == unit_name:
        value = value[:-len(unit_name)]
    return value


def fill_worksheet(workbook, city, prefix_path):
    bold = workbook.add_format({'bold': True})
    worksheet = workbook.add_worksheet(city)
    column_widths = [0] * len(KEY_MAP)
    # set titles
    for idx_col, title in enumerate(KEY_MAP):
        worksheet.write(0, idx_col, title, bold)
        column_widths[idx_col] = max(column_widths[idx_col],
                                     visual_length(title))
    # fill content
    for idx, path in enumerate(
            glob.glob(os.path.join(prefix_path, "**/*.json"))):
        obj = json.load(open(path))
        for idx_col, key in enumerate(KEY_MAP.values()):
            value = obj[key].strip()
            if key == u"area":
                value = strip_unit_name(value, UNIT_NAME_AREA)
            elif key == u"PM_fee":
                value = strip_unit_name(value, UNIT_NAME_PMFEE)
            worksheet.write(idx + 1, idx_col, value)
            column_widths[idx_col] = max(column_widths[idx_col],
                                         visual_length(value))
    # set column widths
    for idx_col, width in enumerate(column_widths):
        column_name = chr(ord('A') + idx_col)
        worksheet.set_column("{0}:{0}".format(column_name), width)

if __name__ == "__main__":
    workbook = xlsxwriter.Workbook(os.path.join(BASE_DIR, 'houses.xlsx'))
    for city in get_city_list():
        path = os.path.join(BASE_DIR, "data", city)
        fill_worksheet(workbook, city, path)
    workbook.close()

