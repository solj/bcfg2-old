'''This module implements a package management scheme for all images'''
__revision__ = '$Revision$'

import logging
import re
import Bcfg2.Server.Plugin
import lxml

logger = logging.getLogger('Bcfg2.Plugins.Pkgmgr')


class FuzzyDict(dict):
    fuzzy = re.compile('(?P<name>.*):(?P<alist>\S+(,\S+)*)')

    def __getitem__(self, key):
        if isinstance(key, str):
            mdata = self.fuzzy.match(key)
            if mdata:
                return dict.__getitem__(self, mdata.groupdict()['name'])
        else:
            print("got non-string key %s" % str(key))
        return dict.__getitem__(self, key)

    def has_key(self, key):
        if isinstance(key, str):
            mdata = self.fuzzy.match(key)
            if self.fuzzy.match(key):
                return dict.has_key(self, mdata.groupdict()['name'])
        return dict.has_key(self, key)

    def get(self, key, default=None):
        try:
            return self.__getitem__(key)
        except:
            if default:
                return default
            raise


class PNode(Bcfg2.Server.Plugin.INode):
    """PNode has a list of packages available at a
    particular group intersection.
    """
    splitters = {'rpm': re.compile('^(.*/)?(?P<name>[\w\+\d\.]+(-[\w\+\d\.]+)*)-' + \
                                  '(?P<version>[\w\d\.]+-([\w\d\.]+))\.(?P<arch>\S+)\.rpm$'),
                 'encap': re.compile('^(?P<name>[\w-]+)-(?P<version>[\w\d\.+-]+).encap.*$')}
    ignore = ['Package']

    def Match(self, metadata, data, entry=lxml.etree.Element("None")):
        """Return a dictionary of package mappings."""
        if self.predicate(metadata, entry):
            for key in self.contents:
                try:
                    data[key].update(self.contents[key])
                except:
                    data[key] = FuzzyDict()
                    data[key].update(self.contents[key])
            for child in self.children:
                child.Match(metadata, data)

    def __init__(self, data, pdict, parent=None):
        # copy local attributes to all child nodes if no local attribute exists
        if 'Package' not in pdict:
            pdict['Package'] = set()
        for child in data.getchildren():
            for attr in [key for key in list(data.attrib.keys())
                         if key != 'name' and key not in child.attrib]:
                try:
                    child.set(attr, data.get(attr))
                except:
                    # don't fail on things like comments and other immutable elements
                    pass
        Bcfg2.Server.Plugin.INode.__init__(self, data, pdict, parent)
        if 'Package' not in self.contents:
            self.contents['Package'] = FuzzyDict()
        for pkg in data.findall('./Package'):
            if 'name' in pkg.attrib and pkg.get('name') not in pdict['Package']:
                pdict['Package'].add(pkg.get('name'))
            if pkg.get('name') != None:
                self.contents['Package'][pkg.get('name')] = {}
                if pkg.getchildren():
                    self.contents['Package'][pkg.get('name')]['__children__'] \
                                                                          = pkg.getchildren()
            if 'simplefile' in pkg.attrib:
                pkg.set('url', "%s/%s" % (pkg.get('uri'), pkg.get('simplefile')))
                self.contents['Package'][pkg.get('name')].update(pkg.attrib)
            else:
                if 'file' in pkg.attrib:
                    if 'multiarch' in pkg.attrib:
                        archs = pkg.get('multiarch').split()
                        srcs = pkg.get('srcs', pkg.get('multiarch')).split()
                        url = ' '.join(["%s/%s" % (pkg.get('uri'),
                                                   pkg.get('file') % {'src':srcs[idx],
                                                                      'arch':archs[idx]})
                                        for idx in range(len(archs))])
                        pkg.set('url', url)
                    else:
                        pkg.set('url', '%s/%s' % (pkg.get('uri'),
                                                  pkg.get('file')))
                if pkg.get('type') in self.splitters and pkg.get('file') != None:
                    mdata = self.splitters[pkg.get('type')].match(pkg.get('file'))
                    if not mdata:
                        logger.error("Failed to match pkg %s" % pkg.get('file'))
                        continue
                    pkgname = mdata.group('name')
                    self.contents['Package'][pkgname] = mdata.groupdict()
                    self.contents['Package'][pkgname].update(pkg.attrib)
                    if pkg.attrib.get('file'):
                        self.contents['Package'][pkgname]['url'] = pkg.get('url')
                        self.contents['Package'][pkgname]['type'] = pkg.get('type')
                        if pkg.get('verify'):
                            self.contents['Package'][pkgname]['verify'] = pkg.get('verify')
                        if pkg.get('multiarch'):
                            self.contents['Package'][pkgname]['multiarch'] = pkg.get('multiarch')
                    if pkgname not in pdict['Package']:
                        pdict['Package'].add(pkgname)
                    if pkg.getchildren():
                        self.contents['Package'][pkgname]['__children__'] = pkg.getchildren()
                else:
                    self.contents['Package'][pkg.get('name')].update(pkg.attrib)


class PkgSrc(Bcfg2.Server.Plugin.XMLSrc):
    """PkgSrc files contain a PNode hierarchy that
    returns matching package entries.
    """
    __node__ = PNode
    __cacheobj__ = FuzzyDict


class Pkgmgr(Bcfg2.Server.Plugin.PrioDir):
    """This is a generator that handles package assignments."""
    name = 'Pkgmgr'
    __version__ = '$Id$'
    __author__ = 'bcfg-dev@mcs.anl.gov'
    __child__ = PkgSrc
    __element__ = 'Package'

    def HandleEvent(self, event):
        '''Handle events and update dispatch table'''
        Bcfg2.Server.Plugin.XMLDirectoryBacked.HandleEvent(self, event)
        for src in list(self.entries.values()):
            for itype, children in list(src.items.items()):
                for child in children:
                    try:
                        self.Entries[itype][child] = self.BindEntry
                    except KeyError:
                        self.Entries[itype] = FuzzyDict([(child,
                                                          self.BindEntry)])

    def BindEntry(self, entry, metadata):
        """Bind data for entry, and remove instances that are not requested."""
        pname = entry.get('name')
        Bcfg2.Server.Plugin.PrioDir.BindEntry(self, entry, metadata)
        if entry.findall('Instance'):
            mdata = FuzzyDict.fuzzy.match(pname)
            if mdata:
                arches = mdata.group('alist').split(',')
                [entry.remove(inst) for inst in \
                 entry.findall('Instance') \
                 if inst.get('arch') not in arches]

    def HandlesEntry(self, entry, metadata):
        return entry.tag == 'Package' and entry.get('name').split(':')[0] in list(self.Entries['Package'].keys())

    def HandleEntry(self, entry, metadata):
        self.BindEntry(entry, metadata)
