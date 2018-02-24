# -*- coding: utf-8 -*-
"""
Created on Thu Oct 26 14:06:44 2017

@author: Will
读取和探索样本数据
"""

import xml.etree.cElementTree as ET
import re
from collections import defaultdict 
import codecs
import sys

ROAD_ABBREVIATION_PATTERN = re.compile(r'\b(\S+\.)$')
ROAD_ABBREVIATION_ENDS = re.compile(r'\b(Rd|St|Ave)$')
LOWER_COLON = re.compile(r'^([a-z]|_)*:([a-z]|_)*$')
PROBLEMCHARS = re.compile(r'[=\+/&<>;\'"\?%#$@\,\. \t\r\n]')
            
INFO_DATA_FILE = "info_data.txt"  

def process_map(filename, colon_keys, problematic_keys, streets, abbr_street_dict, postcodes):
    for _, element in ET.iterparse(filename, events=("start",)):
        if (element.tag == "way") or (element.tag == "node"):
            for tag in element.iter("tag"):
                v = tag.attrib['v'].strip()
                k = tag.attrib['k'].strip()
                key_category(k, colon_keys, problematic_keys)
                #街道
                if k == "addr:street":
                    streets.add(v)
                    check_abbr_street(abbr_street_dict, v)    
                #合法的上海邮编以20开头的6位数字
                if k == "addr:postcode" and (len(v) != 6 or not v.startswith('20')):
                    postcodes.add(v)   

#查找带冒号的键名和非法键名
def key_category(k, colon_keys, problematic_keys):
    if LOWER_COLON.search(k):
        colon_keys.add(k)
    elif PROBLEMCHARS.search(k):
        problematic_keys.add(k)

#查找英文简写路名
def check_abbr_street(abbr_street_dict, v):
    m = ROAD_ABBREVIATION_PATTERN.search(v)
    if (m):
       abbr_street_dict[m.group(1)].add(v)   
    else:
        m = ROAD_ABBREVIATION_ENDS.search(v)
        if (m):
            abbr_street_dict[m.group(1)].add(v)  
            
def write_set(filename, header, datas):
    with codecs.open(filename,'a',encoding='utf-8') as f:
        f.write(header)
        f.write('\n=========\n')
        for item in datas:
            f.write(item.decode('utf-8'))
            f.write('\n') 
        
def write_dict(filename, header, datas):
    with codecs.open(filename,'a',encoding='utf-8') as f:
        f.write(header)
        f.write('\n=========\n')
        for key,value in datas.items():
            f.write(key + ":")
            f.write('\n')
            for item in value:
               f.write(item.decode('utf-8'))
               f.write('\n') 

def test():
    abbr_street_dict = defaultdict(set)
    streets = set()
    postcodes = set()
    problematic_keys = set()
    colon_keys = set()
    process_map('sample.osm', colon_keys, problematic_keys, streets, abbr_street_dict, postcodes)
    #结果输出到文件
    write_set(INFO_DATA_FILE, "colon_keys", colon_keys)
    write_set(INFO_DATA_FILE, "problematic_keys", problematic_keys)
    write_set(INFO_DATA_FILE, "streets", streets)
    write_dict(INFO_DATA_FILE, "abbr_street_dict", abbr_street_dict)
    write_set(INFO_DATA_FILE, "postcodes", postcodes)

if __name__ == "__main__": 
    reload(sys)
    sys.setdefaultencoding('utf-8')
    test()