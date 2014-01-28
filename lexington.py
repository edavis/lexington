#!/usr/bin/env python

"""
lexington.py -- an OPML-based website generator
"""

import argparse
import requests
from lxml import etree

def render_outline(node):
    print ('render_outline', node.get('text'))

def render_link(node):
    print ('render_link', node.get('text'))

def render_thread(node):
    print ('render_thread', node.get('text'))

def render_index(node):
    print ('render_index', node.get('text'))

render_types = {
    'outline': render_outline,
    'link': render_link,
    'thread': render_thread,
}

def render(node, depth=1):
    text = node.get('text')
    terminal = node.get('type') in render_types

    # Render a terminal node.
    if terminal:
        func = render_types[node.get('type')]
        func(node)

    # Render an index node.
    #
    # When that's done, restart the rendering process using the
    # current node's first child.
    #
    # I think this could overflow on very deep OPML files but I've
    # never had any problems.
    elif len(node) and not terminal:
        render_index(node)
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
    args = parser.parse_args()

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
