import sys
import xml.etree.cElementTree as ET
import copy
import types
import json
import os.path
import argparse
import urllib

from pprint import pprint

def indexMRMLNodesById(root, selector='.'):
    mrmlTable = {}

    for elem in root.findall(selector):
        mrmlNode = copy.copy(elem.attrib)
        mrmlNode['_tag'] = elem.tag
        mrmlTable[elem.get('id')] = mrmlNode
    return mrmlTable


def buildMRMLChildren(mrml):
    for i, t in mrml.iteritems():
        try:
            parentNodeRef = t['parentNodeRef']
        except KeyError:
            t['isRoot'] = True
            continue

        t['isRoot'] = False
        parent = mrml[parentNodeRef]
        try:
            children = parent['children']
        except KeyError:
            children = parent['children'] = []

        if i not in children:
            children.append(i)


def getModelFilenameFromMRML(table, node):
    if node.has_key('associatedNodeRef'):
        node = table[node['associatedNodeRef']]

    if node.has_key('storageNodeRef'):
        storageNode = table[node['storageNodeRef']]
        return storageNode['fileName']

    return None

def getColorFromMRML(table, node):
    if node.has_key('displayNodeID'):
        maybeDisplayNode = table[node['displayNodeID']]
        if maybeDisplayNode['_tag'] == 'ModelDisplay':
            return convertModelDisplayNodeColorToCSS3(maybeDisplayNode)
        else:
            # it is actually a model node
            sneakyDisplayNode = table[maybeDisplayNode['displayNodeRef']]
            return convertModelDisplayNodeColorToCSS3(sneakyDisplayNode)

    if node.has_key('associatedNodeRef'):
        modelDisplayNode = table[table[node['associatedNodeRef']]['displayNodeRef']]
        return convertModelDisplayNodeColorToCSS3(modelDisplayNode)        

    return None

def getNameFromMRML(table, node):
    tag = node['_tag']
    if tag != 'ModelHierarchy':
        return node['name']

    if not node.has_key('associatedNodeRef'):
        return node['name']

    associatedNodeRef = node['associatedNodeRef']
    associatedNodeRefName = table[associatedNodeRef]['name']
    if associatedNodeRefName.startswith('Model_'):
        return associatedNodeRefName.split('_', 2)[2]
    else:
        return associatedNodeRefName

def convertColorToCSS3(r, g, b, t=255):
    return 'rgba(%d,%d,%d,%f)' % (int(r), int(g), int(b), float(t)/255.0)


def convertModelDisplayNodeColorToCSS3(n):
    color = n['color']
    opacity = float(n['opacity'])
    v = [int(255.0*float(x)) for x in color.split()]
    if opacity == 1.0:
        return 'rgb(%d,%d,%d)' % tuple(v)
    else:
        v.append(opacity)
        return 'rgba(%d,%d,%d,%f)' % tuple(v)


def createMRMLIdToHAWGIdTable(mrml):
    derivedToMRMLNodeTable = {}
    for mrmlId, t in mrml.iteritems():
        if t['_tag'] != 'ModelHierarchy':
            continue
        derivedId = '#%s' % quoteName(getNameFromMRML(mrml, t))
        if not derivedToMRMLNodeTable.has_key(derivedId):
            derivedToMRMLNodeTable[derivedId] = [mrmlId]
        else:
            derivedToMRMLNodeTable[derivedId].append(mrmlId)

    mrmlToHawgIdTable = {}
    for derivedId, mrmlIds in derivedToMRMLNodeTable.iteritems():
        for i, mId in enumerate(mrmlIds):
            if len(mrmlIds) == 1:
                uniqueId = derivedId
            else:
                uniqueId = '%s__%d' % (derivedId, i)
            mrmlToHawgIdTable[mId] = uniqueId

    return mrmlToHawgIdTable
    
def getVolumes(mrml):
    volumes = []
    labelVolumes = []
    for mrmlId, t in mrml.iteritems():
        tag = t['_tag']
        if tag not in ('Volume', 'LabelMapVolume'):
            continue

        if (tag == 'LabelMapVolume' or 
            (t.has_key('labelMap') and t['labelMap'] == '1')):
            target = labelVolumes
        else:
            target = volumes

        target.append({ 
            'name': t['name'],
            'fileName': mrml[t['storageNodeRef']]['fileName']
        })
    return (volumes, labelVolumes)

def buildProtoHAWGNodes(mrmlTable, atlasName, labelDir, modelDir, imageDir):
    hierarchyRoots = []
    hawgTable = {}
    headerNode = {
        '@id': '#__header__',
        '@type': 'Header',
        'root': hierarchyRoots,
        'title': atlasName
        }

    volumes, labelVolumes = getVolumes(mrmlTable)
    hawgTable[headerNode['@id']] = headerNode

    headerNode['backgroundImage'] = []

    for v in volumes:
        fn = v['fileName']
        if imageDir:
            fn = os.path.join(imageDir, os.path.basename(fn))
        headerNode['backgroundImage'].append(fn)

    if len(labelVolumes) == 0:
        labelFilename = None
    else:   
        fn = labelVolumes[0]['fileName']
        if labelDir:
            fn = os.path.join(labelDir, os.path.basename(fn))
        labelFilename = headerNode['labelImage'] = fn

    MRMLToHAWGId = createMRMLIdToHAWGIdTable(mrmlTable)
    defectiveNodes = set()

    for t in mrmlTable.itervalues():
        if t['_tag'] != 'ModelHierarchy':
            continue
        hawgId = MRMLToHAWGId[t['id']]


        node = {'@id' : hawgId }
        textName = getNameFromMRML(mrmlTable, t).replace('_', ' ')
        setIfNotNone(node, 'name', textName)
        setIfNotNone(node, 'color', getColorFromMRML(mrmlTable, t))
        setIfNotNone(node, 'modelFilename', getModelFilenameFromMRML(mrmlTable, t))

        if node.has_key('modelFilename'):
            modelBasename = os.path.basename(node['modelFilename'])
            if modelDir:
                newModelFilename = os.path.join(modelDir, modelBasename)
                node['modelFilename'] = newModelFilename
            node['labelNumber'] = modelBasename.split('_', 2)[1]
        if labelFilename: 
            node['labelImage'] = labelFilename

        hawgTable[node['@id']] = node

        if t.has_key('children'):
            namesOfChildren = sorted((MRMLToHAWGId[c] for c in t['children']))
            node['member'] = list(set(namesOfChildren))
            node['@type'] = 'Group'
        else:
            node['@type'] = 'Structure'

        if t['isRoot']:
            hierarchyRoots.append(hawgId)
        if node.has_key('modelFilename'):
            if not os.path.isfile(node['modelFilename']):
                print >> sys.stderr, "warning: removing node %s because its datafile %s doesn't exist" % (node['@id'], node['modelFilename'])
                
                defectiveNodes.add(hawgId)

    # remove defective nodes:
    for d in defectiveNodes:
        del hawgTable[d]
        
    for node in hawgTable.itervalues():
        if node.has_key('member'):
            node['member'] = list(set(node['member']) - defectiveNodes)

    return hawgTable


def quoteName(name):
    return urllib.quote(name.replace(' ', '_'))

def listify(d, k):
    try:
        val = d[k]
    except KeyError:
        return []

    return val if isinstance(val, list) else [val]

def insertNode(table, node):
    table[node['@id']] = node


def expandHAWG(proto, rootURL=''):
    output = copy.copy(proto)

    # BaseId
    baseId = '#_urlBase'
    base = {
        '@id': baseId,
        '@type': 'BaseURL',
        'url': rootURL
        }

    insertNode(output, base)

    header = output['#__header__']
    bgImage = listify(header, 'backgroundImage')
    newImages = []
    for i, img in enumerate(bgImage):
        bgimgid = '#_bgImageSrc%d' % i
        newImages.append(bgimgid)
        dataSource = {
            '@id': bgimgid,
            '@type': 'DataSource',
            'mimeType': 'application/x-nrrd',
            'source': img,
            'baseURL': '#_urlBase'
            }
        insertNode(output, dataSource)

    # fix annotations
    for n in output.values():
        if n['@type'] in ('Structure', 'Group'):
            n['annotation'] = {'name': n['name']}
            del n['name']

            if n.has_key('color'):
                n['renderOption'] = {'color': n['color']}
                del n['color']

    # create datasources
    if header.has_key('labelImage'):

        labelDataSourceId = '#_LabelDS'
        labelDataSource = {
            '@id': labelDataSourceId,
            '@type': 'DataSource',
            'source': header['labelImage'],
            'mimeType': 'application/x-nrrd',
            'baseURL': '#_urlBase'
        }
        del header['labelImage']
        insertNode(output, labelDataSource)
        del header['labelImage']
    else:
        labelDataSource = None

    for n in output.values():
        if n['@type'] in ('Structure'):
            modelDataSourceId = '%s_ModelDS' % n['@id']
            modelDataSource = {
                '@id': modelDataSourceId,
                '@type': 'DataSource',
                'mimeType': 'application/octet-stream',
                'source': n['modelFilename'],
                'baseURL': '#_urlBase'
                }
            insertNode(output, modelDataSource)
            sourceSelector = [
                {
                    '@type': [ 'Selector', 'GeometrySelector'],
                    'dataSource': modelDataSourceId,
                    'authoritative': False
                    }]
            if labelDataSource:
                sourceSelector.append({
                    '@type': [ 'Selector', 'LabelMapSelector'],
                    'dataKey': int(n['labelNumber']),
                    'dataSource': labelDataSourceId,
                    'authoritative': True
                })

            n['sourceSelector'] = sourceSelector
            del n['labelImage']
            del n['labelNumber']
            del n['modelFilename']

    for n in output.values():
        if n['@type'] in ('Group'):
            del n['labelImage']

    header['backgroundImage'] = newImages

    return output

def setIfNotNone(d, attr, value):
    if value != None:
        d[attr] = value

def getStructures(hawg):
    return [v['@id'] for v in hawg.values() if v['@type'] in ('Group', 'Structure')]

def verify(hawg):
    nodesInTrees, allOK = checkTreeStructure(hawg)
    allStructures = set(getStructures(hawg))
    orphaned = allStructures - nodesInTrees
    if orphaned:
        print >>sys.stderr, "orphaned nodes: %s" % list(orphaned)
    checkDataSourcesExist(hawg)

def getChildren(hawg, nodeName):
    return hawg[nodeName].get('member', [])

def checkDataSourcesExist(hawg):
    allOK = True
    for ds in [v for v in hawg.itervalues() if  v['@type'] == 'DataSource']:
        if not os.path.isfile(ds['source']):
            print >> sys.stderr, "DataSource %s: file %s does not exist" % (ds['@id'], ds['source'])
            allOK = False
    return allOK

def checkTreeStructure(hawg):
    allOK = True
    allTraversed = set()
    for treeRoot in hawg['#__header__']['root']:
        traversed = set()
        toTraverse = set([treeRoot])
        while toTraverse:
            nextGen = set()
            for t in toTraverse:
                # check for dups
                c = getChildren(hawg, t)
                sc = set(c)
                if len(c) != len(sc):
                    print >>sys.stderr, "node %s has one or more duplicate children" % t
                    allOK = False

                # check for missing children
                for cc in sc:
                    if not hawg.has_key(cc):
                        print >>sys.stderr, "node %s has child %s that doesn't exist" % (t, cc)
                
                # check for loops
                for cc in sc:
                    if cc in traversed:
                        print >>sys.stderr, "node %s has child %s that causes a loop" % (t, cc)
                        allOK = False
                    else:
                        nextGen.add(cc)

            traversed |= toTraverse
            toTraverse = nextGen
        allTraversed.update(traversed)
    return (allTraversed, allOK)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='MRML to proto HAWG')
    parser.add_argument('-l', '--labeldir', default='')
    parser.add_argument('-m', '--modeldir', default='')
    parser.add_argument('-i', '--imagedir', default='')
    parser.add_argument('-r', '--rooturl', default='')
    parser.add_argument('-n', '--name', default='')
    parser.add_argument('-o', '--output', default='atlasStructure.json')

    parser.add_argument('mrmlfile')
    conf = parser.parse_args()

    if not conf.name:
        conf.name = os.path.splitext(os.path.basename(conf.mrmlfile))[0]

    xmlTree = ET.parse(conf.mrmlfile)
    xmlRoot = xmlTree.getroot()

    mrmlNodeTable = indexMRMLNodesById(xmlRoot, './*')
    buildMRMLChildren(mrmlNodeTable)

    protoHAWG = buildProtoHAWGNodes(mrmlNodeTable, conf.name, 
                                    conf.labeldir, conf.modeldir, conf.imagedir)

    expandedHAWG = expandHAWG(protoHAWG, conf.rooturl)
    verify(expandedHAWG)
    with open(conf.output, 'w+') as fp:
        json.dump(expandedHAWG.values(), fp, sort_keys=True,
                        indent=4, separators=(',', ': '))
