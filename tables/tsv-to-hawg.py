import argparse
import sys
import json
import os.path
import re
import csv

class ModelInfo(object):
    pass

def main(modelInfoFile):
    modelInfo = readModelInfo(modelInfoFile)
    hawg = buildHAWGNodes(modelInfo, 'OASIS-TRT-20-1', ['Atlas/OASIS-TRT-20-1_in_MNI152.nrrd'])
    json.dump(hawg.values(), sys.stdout, sort_keys=True,
                        indent=4, separators=(',', ': '))


def insertNode(table, node):
    table[node['@id']] = node

def mkDataSource(id, source, baseURL=None):
    ext = os.path.splitext(source)[1]
    if ext == 'nrrd':
        mimeType = 'application/x-nrrd'
    elif ext == 'vtk':
        mimeType = 'application/octet-stream'
    else:
        mimeType = 'application/octet-stream'

    ret = {
        '@id': id,
        '@type': 'DataSource',
        'mimeType': mimeType,
        'source': source
    }
    if baseURL:
        ret['baseURL'] = baseURL
    return ret


def buildHAWGNodes(modelInfo, atlasName, bgImageFilenames):
    hierarchyRoots = []
    hawgTable = {}
    backgroundImages = []
    headerNode = {
        '@id': '#__header__',
        '@type': 'Header',
        'root': hierarchyRoots,
        'title': atlasName,
        'backgroundImage': backgroundImages
    }
    insertNode(hawgTable, headerNode)

    labelIdTable = {}
    labelFilenames = getLabelFilenames(modelInfo)
    for i, img in enumerate(labelFilenames):
        labelId = '#_labelSrcDS%d' % i
        labelIdTable[img] = labelId
        insertNode(hawgTable, mkDataSource(labelId, img))
    
    for i, img in enumerate(bgImageFilenames):
        bgId = '#_bgImageSrc%d' % i
        insertNode(hawgTable, mkDataSource(bgId, img))
        backgroundImages.append(bgId)

    atlasMembers = []
    atlasRoot = {
        '@id': '#_atlasRoot',
        '@type': 'Group',
        'member': atlasMembers,
        'annotation': {
            'name': atlasName
        }
    }
    hierarchyRoots.append('#_atlasRoot')
    insertNode(hawgTable, atlasRoot)
    for m in modelInfo.itervalues():
        structureId = "#%s" % m['id']
        structure = {
            '@id': structureId,
            '@type': 'Structure',
            'annotation': {
                'name': m['textLabel']
            },
            'renderOption': {
                'color': m['color']
            }
        }
        modelDataSourceId = '#%s_ModelDS' % m['id']
        insertNode(hawgTable, mkDataSource(modelDataSourceId, m['modelFilename']))
        sourceSelector = [
            {
                '@type': ['Selector', 'LabelMapSelector'],
                'dataKey': int(m['labelNumber']),
                'dataSource': labelIdTable[m['labelFilename']],
                'authoritative': True
            },
            {
                '@type': ['Selector', 'GeometrySelector'],
                'dataSource': modelDataSourceId,
                'authoritative': False
            }
        ]
        structure['sourceSelector'] = sourceSelector
        insertNode(hawgTable, structure)
        atlasMembers.append(structureId)

    atlasMembers.sort()
    return hawgTable



def getLabelFilenames(modelInfo):
    return list(set([m['labelFilename'] for m in modelInfo.itervalues()]))

def readModelInfo(modelInfoFile):
    with open(modelInfoFile, 'rU') as fp:
        reader = csv.DictReader(fp, dialect='excel-tab')
        return {row['id']: row for row in reader}

if __name__ == '__main__':
    main(sys.argv[1])

            