# -*- coding: utf-8 -*-
"""
Created on Fri Oct 27 11:07:46 2017

@author: Will
清理和保存数据
"""

import csv
import codecs
import pprint
import re
import xml.etree.cElementTree as ET
import sys

import cerberus

import schema

OSM_PATH = "shanghai_china.osm"

NODES_PATH = "nodes.csv"
NODE_TAGS_PATH = "nodes_tags.csv"
WAYS_PATH = "ways.csv"
WAY_NODES_PATH = "ways_nodes.csv"
WAY_TAGS_PATH = "ways_tags.csv"

#带冒号的k值
LOWER_COLON = re.compile(r'^([a-z]|_)+:([a-z]|_)+')
#无效的k值
PROBLEMCHARS = re.compile(r'[=\+/&<>;\'"\?%#$@\,\. \t\r\n]')
#上海邮编正则表达式
POST_CODE_PATTERN = re.compile(r'20\d{4}')
#至少一个空格
SPACE_PATTERN = re.compile(r'\s+')                             
                            
#结尾的拼音Lu/lu正则表达式
PATTERN_LU_AT_END = re.compile(r'\bLu|lu$')
#中文路名正则表达式
CHINESE_ADDR_PATTERN = re.compile(ur'[\u4e00-\u9fa5]+\s*\d*\s*[\u4e00-\u9fa5]*') 

#路名和全称映射
STREET_ABBR_MAPPING = { "St":"Street",
            "St.":"Street",
            "road":"Road",
            "rd":"Road",
            "Rd":"Road",
            "Rd.":"Road",
            "Ave":"Avenue",
            "Ave.":"Avenue",
            "Hwy":"Highway",
            "Hwy.":"Highway"
            }
#方向简写和全称映射
DIRECTION_ABBR_MAPPING = { "(N)":"North",
            "(N.)":"North",
            "(North)":"North",
            "(north)":"North",
            "(S)":"South",
            "(S.)":"South",
            "(South)":"South",
            "(south)":"South",
            "(W.)":"West",
            "(W)":"West",
            "(West)":"West",
            "(west)":"West",
            "(E)":"East",
            "(E.)":"East",
            "(East)":"East",
            "(east)":"East",
            }

SCHEMA = schema.schema

# Make sure the fields order in the csvs matches the column order in the sql table schema
NODE_FIELDS = ['id', 'lat', 'lon', 'user', 'uid', 'version', 'changeset', 'timestamp']
NODE_TAGS_FIELDS = ['id', 'key', 'value', 'type']
WAY_FIELDS = ['id', 'user', 'uid', 'version', 'changeset', 'timestamp']
WAY_TAGS_FIELDS = ['id', 'key', 'value', 'type']
WAY_NODES_FIELDS = ['id', 'node_id', 'position']

#需要转换成整形和浮点型的字段
INT_FIELDS = ['id', 'uid', 'changeset']
FLOAT_FIELDS = ['lat', 'lon']

#提取标签属性                     
def make_attribs(element, dict):
    for key, value in element.attrib.items():
        if (key in NODE_FIELDS):
            if (key in INT_FIELDS):
                dict[key] = int(value)
            if (key in FLOAT_FIELDS):
                dict[key] = float(value)
            else:
                dict[key] = value

#处理tag子标签        
def make_child_tag(element, tags, default_tag_type='regular'):
    id = element.attrib["id"]
    temp_list = []
    for tag in element.iter("tag"):
        data = {"id" : id}
        k = pre_process_value(tag.attrib["k"])
        if (not PROBLEMCHARS.search(k)):
            v = pre_process_value(tag.attrib["v"])
            if (LOWER_COLON.search(k)):
                if (k == "addr:street"):
                    v = process_address(v)
                if (k == "addr:postcode"):
                    v = process_postcode(v)
                    #邮编属于非上海地区，过滤此数据
                    if (v is None):
                        return
                if (k == "name:en"):
                    #更新英文路名中的一些简写
                    v = update_abbr_word(v)
                type, second = k.split(":", 1)
                data["key"] = second
                data["type"] = type
            else:
                data["key"] = k
                data["type"] = default_tag_type
            data["value"] = v
            temp_list.append(data)
        
    tags.extend(temp_list)

#预处理xml属性值，主要是消除前后空格和无用的xml实体
def pre_process_value(v):
    #消除字符中多余的空格和换行
    v = v.strip()     
    v = SPACE_PATTERN.sub(" ", v)
        
    return v

#处理地址
def process_address(v):
    
    #如果有中英文混合地址，只保留中文地址
    m = CHINESE_ADDR_PATTERN.search(v.decode("utf-8")) 
    if m:
        v = m.group()
    
    v = update_abbr_word(v)    
    
    return v

#处理和提取上海地区邮政编码，否则返回None
def process_postcode(v):
    m = POST_CODE_PATTERN.search(v)
    if m:
        v = m.group()
    else:
        v = None
        
    return v    

#替换英文简写，和不规范的英文地址
def update_abbr_word(v):
    new_sort = []
    
    #替换Lu/lu
    v = PATTERN_LU_AT_END.sub("Road", v)
    
    words = v.split()
    for i in range(len(words)):
        if words[i] in STREET_ABBR_MAPPING:
            #用全称替换英文简写的路
            words[i] = STREET_ABBR_MAPPING[words[i]] 
        if words[i] in DIRECTION_ABBR_MAPPING:
            #用全称替换英文简写的东西南北
            words[i] = DIRECTION_ABBR_MAPPING[words[i]]    
        new_sort.append(words[i])
    v = " ".join(new_sort)   
            
    return v

#处理way标签中的nd子标签   
def make_node_tag(element, tags):
    id = element.attrib["id"]
    for idx,tag in enumerate(element.iter("nd")):
        data = {"id" : id}
        ref = tag.attrib["ref"]
        data['node_id'] = int(ref)
        data['position'] = idx
        tags.append(data) 
        
    return tags

#清理提取数据的主要函数
def shape_element(element, node_attr_fields=NODE_FIELDS, way_attr_fields=WAY_FIELDS,
                  problem_chars=PROBLEMCHARS, default_tag_type='regular'):
    """Clean and shape node or way XML element to Python dict"""

    node_attribs = {}
    way_attribs = {}
    way_nodes = []
    tags = []  

    #读取和处理way和node元素
    if element.tag == 'node':
        make_attribs(element, node_attribs)
        make_child_tag(element, tags, default_tag_type)

        return {'node': node_attribs, 'node_tags': tags}
    elif element.tag == 'way':
        make_attribs(element, way_attribs)
        make_child_tag(element, tags, default_tag_type)
        make_node_tag(element, way_nodes)
        
        return {'way': way_attribs, 'way_nodes': way_nodes, 'way_tags': tags}


#读取xml文件，处理感兴趣的tag
def get_element(osm_file, tags=('node', 'way', 'relation')):
    """Yield element if it is the right type of tag"""

    context = ET.iterparse(osm_file, events=('start', 'end'))
    _, root = next(context)
    for event, elem in context:
        if event == 'end' and elem.tag in tags:
            yield elem
            root.clear()

#验证结果
def validate_element(element, validator, schema=SCHEMA):
    """Raise ValidationError if element does not match schema"""
    if validator.validate(element, schema) is not True:
        field, errors = next(validator.errors.iteritems())
        message_string = "\nElement of type '{0}' has the following errors:\n{1}"
        error_string = pprint.pformat(errors)
        
        raise Exception(message_string.format(field, error_string))

#通过字典方式写入csv文件
class UnicodeDictWriter(csv.DictWriter, object):
    """Extend csv.DictWriter to handle Unicode input"""

    def writerow(self, row):
        super(UnicodeDictWriter, self).writerow({
            k: (v.encode('utf-8') if isinstance(v, unicode) else v) for k, v in row.iteritems()
        })

    def writerows(self, rows):
        for row in rows:
            self.writerow(row)


# ================================================== #
#               Main Function                        #
# ================================================== #
def process_map(file_in, validate):
    """Iteratively process each XML element and write to csv(s)"""

    with codecs.open(NODES_PATH, 'w') as nodes_file, \
         codecs.open(NODE_TAGS_PATH, 'w') as nodes_tags_file, \
         codecs.open(WAYS_PATH, 'w') as ways_file, \
         codecs.open(WAY_NODES_PATH, 'w') as way_nodes_file, \
         codecs.open(WAY_TAGS_PATH, 'w') as way_tags_file:

        nodes_writer = UnicodeDictWriter(nodes_file, NODE_FIELDS)
        node_tags_writer = UnicodeDictWriter(nodes_tags_file, NODE_TAGS_FIELDS)
        ways_writer = UnicodeDictWriter(ways_file, WAY_FIELDS)
        way_nodes_writer = UnicodeDictWriter(way_nodes_file, WAY_NODES_FIELDS)
        way_tags_writer = UnicodeDictWriter(way_tags_file, WAY_TAGS_FIELDS)

        nodes_writer.writeheader()
        node_tags_writer.writeheader()
        ways_writer.writeheader()
        way_nodes_writer.writeheader()
        way_tags_writer.writeheader()

        validator = cerberus.Validator()

        for element in get_element(file_in, tags=('node', 'way')):
            el = shape_element(element)
            if el:
                if validate is True:
                    validate_element(el, validator)

                if element.tag == 'node':
                    nodes_writer.writerow(el['node'])
                    node_tags_writer.writerows(el['node_tags'])
                elif element.tag == 'way':
                    ways_writer.writerow(el['way'])
                    way_nodes_writer.writerows(el['way_nodes'])
                    way_tags_writer.writerows(el['way_tags'])


if __name__ == '__main__':
    # 输出中文问题处理
    reload(sys)
    sys.setdefaultencoding('utf-8')
    
    process_map(OSM_PATH, validate=True)

