#!/usr/bin/env python

"""
lexington.py -- an OPML to HTML processor
"""

import os
import argparse
import requests
from lxml import etree
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

environment = Environment(loader=FileSystemLoader('templates'))

def identifier(node):
    if node.get('name'):
        return node.get('name')
    elif node.get('text'):
        text = node.get('text')
        return text.replace(' ', '-').lower()

def build_path(node):
    if not node.get('type'):
        ancestors = [identifier(node)]
    else:
        ancestors = []
    for ancestor in node.iterancestors('outline'):
        ancestors.insert(0, identifier(ancestor))
    path = ('/'.join(ancestors)).lstrip('/')
    if not node.get('type'):
        return Path('%s/index.html' % path)
    else:
        return Path('%s/%s.html' % (path, identifier(node)))

def render_outline(node):
    return str(node.attrib)

def render_link(node):
    return str(node.attrib)

def render_thread(node):
    return str(node.attrib)

def render_index(node):
    return str(node.attrib)

def write_output(node, content):
    path = build_path(node)
    if not path.parent.is_dir():
        path.parent.mkdir(parents=True)
    with path.open('w') as fp:
        fp.write(content.decode('utf-8'))

render_types = {
    'outline': render_outline,
    'link': render_link,
    'thread': render_thread,
}

def render(node, depth=1):
    text = node.get('text')
    terminal = node.get('type') in render_types

    # TODO skip nodes with isComment=true

    # Render a terminal node.
    if terminal:
        func = render_types[node.get('type')]
        write_output(node, func(node))

    # Render an index node.
    #
    # When that's done, restart the rendering process using the
    # current node's first child.
    #
    # I think this could overflow on very deep OPML files but I've
    # never had any problems.
    elif len(node) and not terminal:
        write_output(node, render_index(node))
        return render(node[0], depth + 1)

    # Move onto the next node.
    #
    # First try the node's next sibling. If the node has no next
    # sibling, keep trying ancestors until one of them has a next
    # sibling and use that.
    #
    # Top-level nodes are at a depth of 1, so if our "ancestor search"
    # hits the <body> element, that means we're done.
    if node.getnext() is not None:
        return render(node.getnext(), depth)
    elif node.getnext() is None:
        parent = node.getparent()
        depth -= 1
        while parent.getnext() is None:
            parent = parent.getparent()
            depth -= 1
            if depth < 1:
                return
        return render(parent.getnext(), depth)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('input')
    parser.add_argument('-o', '--output', default='html')
    args = parser.parse_args()

    output = Path(args.output)
    if not output.is_dir():
        output.mkdir(parents=True)
    os.chdir(str(output))

    if args.input.startswith(('http://', 'https://')):
        resp = requests.get(args.input)
        resp.raise_for_status()
        doc = etree.fromstring(resp.content)
    else:
        doc = etree.parse(args.input).getroot()
    head, body = doc
    assert len(body), 'no outline elements in the body!'
    render(body[0])

if __name__ == '__main__':
    main()
