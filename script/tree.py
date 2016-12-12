"""Objects and functions for manipulating the family tree."""

from datetime import datetime
from common import filter_list, merge_item, select_option, answer_boolean, person_name
from common import SUCCESS, MALE, FEMALE, EMPTYDATE
from covert import setting
import common

person_fmt = "{}{label!s:<15}: {firstname:<35} {prefix:<10} {lastname:<15} {birthdate!s:<15}"

def match_person(label, person, bornin=None, bornbefore=None):
    if not person:
        return
    print(person_fmt.format(' ', label=label, **person))
    # TODO: add jellyfish.fuzzy(lastname) for phonetic searches
    query = {'firstname': ('==', person['firstname']),
             'lastname': ('==', person['lastname'])}
    mode = '='
    bd = person['birthdate']
    if bd:
        birth_date = datetime(bd.year, bd.month, bd.day, 0, 0, 0)
        query.update({'birthdate': ('==', birth_date)})
    elif bornin:
        query.update({'birthdate': ('[]', datetime(bornin, 1, 1), datetime(bornin, 12, 31))})
        mode = '~'
    elif bornbefore:
        query.update({'birthdate': ('<=', bornbefore)})
        mode = '~'
    bp = person['birthplace']
    if bp:
        query.update({'birthplace': ('==', person['birthplace'])})
    result = common.Person.find(query)
    if result:
        for n, r in enumerate(result):
            print(person_fmt.format(mode, label=n+1, **r))
    return result

family_fmt = "{label!s:<15}: {husbandname:<35} {wifename:<35} {marriagedate!s:<15}"

def match_family(family, husband='', wife=''):
    query = {'husbandname': ('==', husband), 'wifename': ('==', wife)}
    result = common.Family.find(query)
    if result:
        for n, r in enumerate(result):
            print(family_fmt.format(label=n+1, **r))
    return result

def filter_person(relations, persons, role, gender=None):
    relation = filter_list(relations, 'type', role)
    if relation:
        person = filter_list(persons, 'pid', relation['person'])
        if gender:
            person['gender'] = gender
        return person
    else:
        return None

compare_fmt = "{:<15}: {!s:<35} {!s:<35} {!s:<35}"

def show(s):
    if isinstance(s, list):
        return "[{}]".format(', '.join([str(el) for el in s]))
    else:
        return str(s)

def update_or_insert_person(role, person_db, person_import):
    if 'age' in person_import:
        del person_import['age']
    if 'pid' in person_import:
        del person_import['pid']
    if person_db:
        print('Persoonskaarten voor {} samenvoegen'.format(role))
        person_merge = merge_item(person_db, person_import)
        if setting.debug:
            print(compare_fmt.format('', 'database', 'import', 'combined'))
            print('-' * 120)
            for key in sorted(person_db.keys()):
                value1 = show(person_db[key])
                value2 = show(person_import.get(key, '-'))
                value3 = show(person_merge.get(key, '-'))
                if key == '_id' or (value1=='' and value2=='' and value3==''):
                    continue
                print(compare_fmt.format(key, value1, value2, value3))
            print('\n')
        person_merge.write(validate=False)
        return person_merge
    else:
        print('Persoonskaart voor {} opslaan'.format(role))
        person_import.write(validate=False)
        return person_import

def update_or_insert_family(family_db, family_import):
    if family_db:
        print('Gezinskaarten samenvoegen')
        family_merge = merge_item(family_db, family_import)
        if setting.debug:
            print(compare_fmt.format('', 'database', 'import', 'combined'))
            print('-' * 120)
            for key in sorted(family_db.keys()):
                value1 = show(family_db[key])
                value2 = show(family_import.get(key, '-'))
                value3 = show(family_merge.get(key, '-'))
                if key == '_id' or (value1=='' and value2=='' and value3==''):
                    continue
                print(compare_fmt.format(key, value1, value2, value3))
            print('\n')
        family_merge.write(validate=False)
        return family_merge
    else:
        print('Gezinskaart opslaan')
        family_import.write(validate=False)
        return family_import

def update_or_insert_source(source):
    if not source:
        return
    result = common.Source.find({'book': source['book']})
    if result:
        return result[0]
    else:
        result = source.write()
        if result['status'] != SUCCESS:
            print('Bron kon niet worden opgeslagen omdat {}'.format(result['data']))
        return source

def link_family_parent(family, role, parent):
    family_ref = common.FamilyRef(family['id'])
    parent_ref = common.PersonRef(parent['id'])
    family[role] = parent_ref
    if 'marriages' in parent:
        if family_ref not in parent['marriages']:
            parent['marriages'].append(family_ref)
    else:
        parent['marriages'] = [family_ref]

def link_family_child(family, child):
    family_ref = common.FamilyRef(family['id'])
    child_ref  = common.PersonRef(child['id'])
    child['family'] = family_ref
    if 'children' in family:
        if child_ref not in family['children']:
            family['children'].append(child_ref)
    else:
        family['children'] = [child_ref]

def select_item(label, options):
    pos = select_option(label, options)
    if pos > 0:
        selected = options[pos-1]
        print(label, 'gevonden:', selected)
        return selected
    else:
        return None

def register_birth(event, persons, relations, source):
    # initialize person and family objects
    child_db = None
    father_db = None
    mother_db = None
    family_db = None
    family = common.Family.empty()
    # extraction and database lookup
    child = filter_person(relations, persons, 'Kind')
    child['birthdate'] = event['date']
    father = filter_person(relations, persons, 'Vader', gender=MALE)
    mother = filter_person(relations, persons, 'Moeder', gender=FEMALE)
    print('geboren op {} in {} (bron: {})'.format(event['date'], event['place'], source))
    print('{}, ouders {} en {}'.format(child, father, mother))
    options = match_person('kind', child, bornin=event['date'].year)
    pos = select_option('Kandidaat voor kind', options)
    if pos > 0:
        child_db = options[pos-1]
        print('Kandidaat voor kind gevonden:', child_db)
        if 'family' in child_db:
            family_db = child_db['family'].lookup()
            print('Gezin:', family_db)
            father_db = family_db['husband'].lookup()
            mother_db = family_db['wife'].lookup()
    husband_name = person_name(father)
    wife_name = person_name(mother)
    family['husbandname'] = husband_name
    family['wifename'] = wife_name
    if not family_db:
        options = match_family(None, husband_name, wife_name)
        family_db = select_item('Kandidaat voor gezin', options)
    if family_db:
        father_db = family_db['husband'].lookup()
        mother_db = family_db['wife'].lookup()
    if father_db:
        print('Gezinskaart levert vader op:', father)
    else:
        options = match_person('vader',  father, bornbefore=event['date'])
        father_db = select_item('Kandidaat voor vader', options)
    if mother_db:
        print('Gezinskaart levert moeder op:', mother_db)
    else:
        options = match_person('moeder',  mother, bornbefore=event['date'])
        mother_db = select_item('Kandidaat voor moeder', options)
    # update or insert vertices
    child_db  = update_or_insert_person('kind',   child_db,  child)
    father_db = update_or_insert_person('vader',  father_db, father)
    mother_db = update_or_insert_person('moeder', mother_db, mother)
    family_db = update_or_insert_family(family_db, family)
    source_db = update_or_insert_source(source)
    # update or insert edges
    if source_db:
        source_ref = common.SourceRef(source_db['id'])
        if 'sources' in child:
            child['sources'].append(source_ref)
        else:
            child['sources'] = [source_ref]
    link_family_child(family_db, child_db)
    link_family_parent(family_db, 'husband', father_db)
    link_family_parent(family_db, 'wife', mother_db)
    child_db.write()
    father_db.write()
    mother_db.write()
    family_db.write()
    if answer_boolean('Doorgaan?'):
        print('\n')
        return
    else:
        raise StopIteration

def register_marriage(event, persons, relations, source):
    relation = filter_list(relations, 'type', 'Bruid')
    if relation:
        bride = filter_list(persons, 'pid', relation['person'])
        bride['gender'] = FEMALE
        # search for age
    relation = filter_list(relations, 'type', 'Bruidegom')
    if relation:
        groom = filter_list(persons, 'pid', relation['person'])
        groom['gender'] = MALE
        # search for age
        # bornbefore = event['date'] - timedelta(days=age*365)
    print('getrouwd op {} in {}: {} ({}) en {} ({}) (bron: {})'.\
          format(event['date'].date(), event['place'],
                 bride, bride['age'], groom, groom['age'], source))
    match_person('bruid',     bride)
    match_person('bruidegom', groom)
    print('\n')

def register_death(event, persons, relations, source):
    # initialize person and family objects
    dead_db = None
    father_db = None
    mother_db = None
    family_db = None
    family = common.Family.empty()
    # extraction and database lookup
    dead = filter_person(relations, persons, 'Overledene')
    dead['deathdate'] = event['date']
    father = filter_person(relations, persons, 'Vader', gender=MALE)
    mother = filter_person(relations, persons, 'Moeder', gender=FEMALE)
    relation = filter_list(relations, 'type', 'other:Relatie')
    if relation:
        partner_id = relation['person1'] if relation['person2']==dead['pid'] else relation['person2']
        partner = filter_list(persons, 'pid', partner_id)
    else:
        partner = None
    if partner:
        note = 'weduwe/naar van: {}'.format(partner)
        if 'notes' in dead:
            dead['notes'].append(note)
        else:
            dead['notes'] = [note]
    else:
        note = ''
    print('overleden op {} in {} (bron: {})'.format(event['date'], event['place'], source))
    print('{}, ouders {} en {} {}'.format(dead, father, mother, note))
    options = match_person('overledene', dead, bornbefore=event['date'].year)
    pos = select_option('Kandidaat voor overledene', options)
    if pos > 0:
        dead_db = options[pos - 1]
        print('Kandidaat voor overledene gevonden:', dead_db)
        if 'family' in dead_db:
            family_db = dead_db['family'].lookup()
            print('Gezin:', family_db)
            father_db = family_db['husband'].lookup()
            mother_db = family_db['wife'].lookup()
        if 'marriages' in dead_db:
            for ref in dead_db['marriages']:
                marriage_db = ref.lookup()
                print('Huwelijk:', marriage_db)
    husband_name = person_name(father)
    wife_name = person_name(mother)
    family['husbandname'] = husband_name
    family['wifename'] = wife_name
    if not family_db:
        options = match_family(None, husband_name, wife_name)
        family_db = select_item('Kandidaat voor gezin', options)
    if family_db:
        father_db = family_db['husband'].lookup()
        mother_db = family_db['wife'].lookup()
    if father_db:
        print('Gezinskaart levert vader op:', father)
    else:
        options = match_person('vader', father, bornbefore=event['date'])
        father_db = select_item('Kandidaat voor vader', options)
    if mother_db:
        print('Gezinskaart levert moeder op:', mother_db)
    else:
        options = match_person('moeder', mother, bornbefore=event['date'])
        mother_db = select_item('Kandidaat voor moeder', options)
    # update or insert vertices
    dead_db = update_or_insert_person('overledene', dead_db, dead)
    father_db = update_or_insert_person('vader', father_db, father)
    mother_db = update_or_insert_person('moeder', mother_db, mother)
    family_db = update_or_insert_family(family_db, family)
    source_db = update_or_insert_source(source)
    # update or insert edges
    if source_db:
        source_ref = common.SourceRef(source_db['id'])
        if 'sources' in dead:
            dead['sources'].append(source_ref)
        else:
            dead['sources'] = [source_ref]
    link_family_child(family_db, dead_db)
    link_family_parent(family_db, 'husband', father_db)
    link_family_parent(family_db, 'wife', mother_db)
    dead_db.write()
    father_db.write()
    mother_db.write()
    family_db.write()
    if answer_boolean('Doorgaan?'):
        print('\n')
        return
    else:
        raise StopIteration
