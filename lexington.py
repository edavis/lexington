#!/usr/bin/env python

"""
lexington.py -- an OPML to HTML processor
"""

import re
import argparse
import requests
from path import path
from lxml import etree
from jinja2 import Environment, FileSystemLoader

# Deep OPML files exceed the max recursion limit, so bump it up.
#
# Any feedback on how to avoid having to do this is very welcome.
import sys; sys.setrecursionlimit(3000)

environment = Environment(loader=FileSystemLoader('../templates'))

class OPML(object):

    """
    An OPML file.

    This class accepts both local filenames and remote URLs.
    """

    def __init__(self, source):
        """
        Parse an OPML file located at source.

        - source (str): Local filename or remote URL of OPML file.
        """
        self.source = source
        self.head, self.body = self.parse(source)
        self.headers = self.parse_headers(self.head)
        assert len(self.body), 'no outline elements found!'

    def render(self, output):
        """
        Render HTML files from the source OPML file into the provided
        directory.

        - output (str): Directory to store HTML files.
        """
        output = path(output)
        output.makedirs_p()
        output.cd()
        return Node(self.body[0], self)

    def parse(self, source):
        """
        Return the root <opml> element from the OPML file.

        - source (str): Local filename or remote URL of OPML file.
        """
        if re.search('https?://', source):
            resp = requests.get(source)
            resp.raise_for_status()
            return etree.fromstring(resp.content)
        else:
            return etree.parse(source).getroot()

    def parse_headers(self, head_element):
        """
        Return the <head> elements from this OPML file as a dict.

        - head_element: Parsed <head> element of OPML file.

        For example:
          <head>
            <title>foo</title>
            <dateModified>XXX</dateModified>
            [...]
          </head>

        Returns:
          {'title': 'foo', 'dateMmodified': 'XXX', ...}
        """
        headers = {}
        for element in head_element:
            headers[element.tag] = element.text
        return headers

class Node(object):

    """
    A single outline node in an OPML file.
    """

    # The node types that we can render
    render_nodetypes = {
        'outline',
        'link',
        'thread',
    }

    def __init__(self, node, opml, process=True):
        """
        Create a Node object.

        - node: An <outline> element.
        - opml: An OPML object.
        - process (bool): Whether to recursively render this node and its
          children. Set to False when gathering the outlines for
          display on the index pages.
        """
        self.node = node
        self.opml = opml
        self.text = node.get('text').decode('utf-8')
        self.context = {
            'head': opml.headers,
        }
        self.context.update(node.attrib)
        # Any descendant of this node that has a type attribute gets
        # displayed on index pages.
        self.index_children = iter(self.node.xpath('.//outline[@type and not(@isComment="true")]'))
        if process:
            self.process(node)

    def __iter__(self):
        return self

    def next(self):
        """
        Iterate over each child of this node that has a type attribute.
        """
        child = next(self.index_children)
        return Node(child, self.opml, process=False)

    def process(self, node):
        """
        Render the this node (if possible) and then move onto the next
        one.

        This method is called from the constructor.

        - node: An <outline> element.

        Once the node has been rendered, move on to the next node in
        this order:

        - If self.node has children, use its first child.
        - If self.node has a next sibling, use that.
        - If self.node has no children and no next siblings, cycle up
          through its parents until one is found that does have a next
          sibling.

        If the "parent search" lands on the <body> element, that means
        we have processed everything in the last summit, so we return
        None which stops all further processing.
        """
        render_node = node.get('type') in self.render_nodetypes
        index_node = len(node) and not render_node

        # Skip commented out nodes entirely
        if node.get('isComment', 'false') == 'true':
            pass
        elif render_node or index_node:
            self.render()
            if index_node:
                return Node(node[0], self.opml)

        if node.getnext() is not None:
            return Node(node.getnext(), self.opml)
        elif node.getnext() is None:
            parent = node.getparent()
            while parent.getnext() is None:
                parent = parent.getparent()
                if parent.tag == 'body':
                    return
            return Node(parent.getnext(), self.opml)

    def path(self):
        """
        Return the destination filename for this node.

        The path is built by prepending each ancestor's identifier (up
        to but excluding the <body>) and joining with a forward slash.

        Render nodes get a single HTML file, index nodes get an
        index.html inside a directory.
        """
        index_node = self.node.get('type') is None
        ancestors = []
        if index_node:
            ancestors.insert(0, self.name())
        for ancestor in self.node.iterancestors('outline'):
            ancestors.insert(0, Node.identifier(ancestor))
        path = '/'.join(ancestors)
        if index_node:
            return u'%s/index.html' % (path)
        else:
            return u'%s/%s.html' % (path, self.name())

    def link(self):
        """
        Return the absolute URL of this node.

        Using absolute URLs lets us avoid keeping track of where we
        are when generating the URL, so it's much simpler.
        """
        return '/%s' % self.path()

    @staticmethod
    def identifier(node):
        """
        Return the node's name attribute (if applicable), otherwise return
        a normalized, innerCase version of the node's text attribute.

        This exists as a static method so it can be used on nodes we
        don't want processed/rendered (e.g., with ancestors when
        building the path).

        - node: An <outline> element.
        """
        def _innerCase(s):
            cleaned = re.sub('[^\w ]', '', s)
            bits = map(str.capitalize, cleaned.split())
            bits[0] = bits[0].lower()
            return u''.join(bits)
        if node.get('name'):
            return node.get('name').decode('utf-8')
        elif node.get('text'):
            return _innerCase(node.get('text'))

    def name(self):
        """
        Return the current node's identifier.

        See Node.identifier() for what exactly this looks for and in
        what order.
        """
        return self.identifier(self.node)

    def body(self):
        """
        Yield each text element in the current node, descending as needed.
        """
        def _iterate(node):
            for element in node:
                text = element.get('text')
                # Ignore rules.
                #
                # This works as skipping past any <rule> also skips
                # its children, so we don't need to catch the
                # particular elements inside a <rule>.
                if text.startswith(('<rule', '</rule')):
                    continue
                yield text
                if len(element):
                    for child in _iterate(element):
                        yield child
        return _iterate(self.node)

    def safe_filename(self, filename):
        """
        Sanitize and prepare the filename we're about to write to.

        In particular:
        - Remove any leading slashes (to keep things written in the output directory)
        - Create any parent directories as needed
        """
        p = path(filename.lstrip('/'))
        p.parent.makedirs_p()
        return p

    def render(self):
        """
        Render the current node and write the output to its path.
        """
        fname = self.safe_filename(self.path())
        node_type = self.node.get('type', 'index')
        template = environment.get_template('%s.html' % node_type)
        self.context.update({
            'node': self,
        })
        content = template.render(self.context)

        with fname.open('w') as fp:
            fp.write(content.encode('utf-8'))

    def __unicode__(self):
        """
        Return this node's text attribute when a unicode string is
        required.
        """
        return self.text

    def __str__(self):
        """
        Return this node's text attribute as a UTF-8 string.
        """
        return unicode(self).encode('utf-8')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('input')
    parser.add_argument('-o', '--output', default='html')
    args = parser.parse_args()

    opml = OPML(args.input)
    opml.render(args.output)
