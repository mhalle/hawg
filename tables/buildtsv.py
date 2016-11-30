import argparse
import sys
import json
import os.path
import re
import csv

# colortable
# labelfile
# bgimage
# output -> stdout
# models

class ModelInfo(object):
    pass

def main(conf):
    colorTable = parseColorTableFile(conf.colortable)
    modelInfo = getModelInfo(conf.models)
    addColorInfo(modelInfo, colorTable)
    addLabelFile(modelInfo, conf.labelfile)
    writeModelInfo(modelInfo)

def writeModelInfo(mi):
    writer = csv.DictWriter(sys.stdout, dialect='excel-tab', 
        fieldnames=['labelNumber', 'id', 'textLabel', 'color', 'modelFilename', 'labelFilename'])
    writer.writeheader()
    for m in sorted(mi.values(), key=lambda x: x.id):
        writer.writerow(m.__dict__)

def addColorInfo(modelInfo, colorTable):
    for k, m in modelInfo.iteritems():
        m.color = colorTable[k]['color']
        
def addLabelFile(modelInfo, lf):
    for m  in modelInfo.itervalues():
        m.labelFilename = lf

def parseModelFilename(m):
    i = ModelInfo()
    i.modelFilename = m
    modelBasename = os.path.basename(m)
    match = re.match(r'Model_([-0-9]+)_(.*?)\.vtk', modelBasename)
    if match:
        i.labelNumber = match.group(1)
        i.textLabel = match.group(2).replace('_', ' ')
        i.id = match.group(2)
    else:
        match = re.match(r'^(.*?)-([0-9]+)', modelBasename)
        i.labelNumber = match.group(2)
        i.textLabel = match.group(1).replace('_', ' ')
        i.id = match.group(1)
    return i

def getModelInfo(modelfiles):
    ret = {}
    for m in modelfiles:
        i = parseModelFilename(m)
        ret[i.labelNumber] = i
    return ret

def parseColorTableFile(filename):
    table = {}
    fp = open(filename, 'rU')
    for line in fp:
        line = line.strip()
        if not line or line[0] == '#':
            continue
        val, name, fr, fg, fb, ft = line.split()
        name = ' '.join(name.split('_'))
        table[val] = dict(name=name, color=convertColorToCSS3(fr, fg, fb, ft))
    fp.close()
    return table

def convertColorToCSS3(r, g, b, t=255):
    return 'rgba(%d,%d,%d,%g)' % (int(r), int(g), int(b), float(t)/255.0)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='create HAWG structure')
    parser.add_argument('--colortable', required=True)
    parser.add_argument('--labelfile', required=True)
    parser.add_argument('--bgimage', action='append', required=True)
    parser.add_argument('models', nargs='+')
    conf = parser.parse_args()
    main(conf)


