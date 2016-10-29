#!/usr/bin/python3

from bisect import bisect_left, bisect_right

doc1 = {
    'd': [{'a': 'alfa', 'b': 'bravo'},
          {'x': 'xray', 'y': 'yankee', 'z': 'zulu'}],
    'p': ['zero', 'one', 'three']
}

doc2 = {'k': doc1, 'l': doc1}

def flatten(doc):
    """flatten(doc) -> newdoc
       Flatten document with hierarchical structure
    """
    newdoc = {}
    for key, value in _flatten(doc, ''):
        newdoc[key] = value
    return newdoc

def _flatten(doc, prefix):
    for key, value in doc.items(): #TODO: use the model's declaration order
        sub_prefix = '{}{}.'.format(prefix, key)
        if isinstance(value, dict):  # embedded document
            yield from _flatten(value, sub_prefix)
        elif isinstance(value, list):  # list of scalars or documents
            if len(value) == 0:  # empty list
                yield prefix + key, value
            elif isinstance(value[0], dict):  # list of documents
                for sub_key, element in enumerate(value):
                    yield from _flatten(element, sub_prefix + str(sub_key) + '.')
            else:  # list of scalars
                for sub_key, element in enumerate(value):
                    yield sub_prefix + str(sub_key), element
        else:  # scalar
            yield prefix + key, value

doc3 = flatten(doc2)

def unflatten(doc):
    """unflatten(doc) -> newdoc
       Unflatten document to (re)create hierarchical structure.
       A flattened document has keys 'a' or 'a.b'. As preparation, the keys are
       transformed into lists (25% faster than keeping them as strings), and
       the document is transformed to a list of 2-tuples, sorted on key.
    """
    lrep = [(key.split('.'), doc[key]) for key in sorted(doc.keys())]
    print("lrep:", lrep)
    return _unflatten(lrep)

def _unflatten(lrep):
    newdoc = {}
    car_list = [elt[0].pop(0) for elt in lrep]  # take first element (car) from each key
    car_set = set(car_list)  # set of (unique) car's is the set of keys of newdoc
    print("car_set:", car_set)
    for key in car_set:
        begin = bisect_left(car_list, key)
        end = bisect_right(car_list, key)
        children = lrep[begin:end]
        if len(children) == 1:
            newdoc[key] = children[0][1]  # scalar
        else:
            newdoc[key] = _unflatten(children)
    if car_set and all([key.isnumeric() for key in car_set]):  # turn dict with numeric keys into list
        print("turn dict into list")
        return [t[1] for t in sorted(newdoc.items(), key=lambda t: int(t[0]))]
    else:
        print("return dict, newdoc:", newdoc)
        return newdoc