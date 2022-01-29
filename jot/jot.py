#!/usr/bin/env python3

"""
JOT is a note taking and task management tool
"""

import os
import sys
import platform
import subprocess
import argparse
import tempfile
import sqlite3
import pydoc
import math
import csv
import shutil

from pathlib import Path
from datetime import datetime


class Jot:
    def __init__(self, **kwargs):
        self.read_config()
        self.connect()
        self.parse_inputs()
        self.main()

    def read_config(self):
        # Define jot dir under home directory
        self.SRC_DIR = Path(__file__).parent
        self.JOT_DIR = Path.home() / '.jot'
        self.JOT_DIR.mkdir(exist_ok=True)

        def_conf = self.SRC_DIR / 'default_config.csv'
        conf = self.JOT_DIR / 'config.csv'

        if conf.exists():
            p = conf
        else:
            p = def_conf

        d = {}
        with open(p, newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                d[row['name']] = row['value'].strip()
        self.config = d

        if p == def_conf:
            self.config['db_dir'] = self.JOT_DIR
            self.write_config(self.config)
            # TODO DELETE IN LATER VERSION--TO MIGRATE existing.sqlites to dat location
            sourcefiles = os.listdir(self.JOT_DIR)
            destinationpath = self.JOT_DIR / 'dat'
            for file in sourcefiles:
                if file.endswith('.sqlite'):
                    shutil.move(self.JOT_DIR / file, self.JOT_DIR / 'dat' / file)

        self.snippet_width = int(d['snippet_width']) # notes column print width
        self.DB_NAME = d['db_name']
        self.DB_DIR = Path(d['db_dir'])
        self.DB = self.DB_DIR / self.DB_NAME

        # see ansi 256 color codes: https://www.ditig.com/256-colors-cheat-sheet
        self.palette = [d['color_line'], d['color_note'], d['color_todo'],
                d['color_done'], d['color_drop'], d['color_part'], d['color_id'],
                d['color_default'], d['color_text']]

        #### windows config
        if platform.system() == 'Windows':
            self.EDITOR = d['win_editor']
            self.colorize = d['win_colorize'] == "True"
            self.view_note_cmd = d['win_view_cmd']
        #### macos
        elif platform.system() == "Darwin":
            self.EDITOR = d['mac_editor']
            self.colorize = d['mac_editor'] == "True"
            self.view_note_cmd = d['mac_view_cmd']
        #### Linux config
        else:
            self.EDITOR = d['unix_editor']
            self.colorize = d['unix_colorize'] == "True"
            self.view_note_cmd = d['unix_view_cmd']
        return(d)

    def write_config(self, config):
        conf_list = []
        for key, val in config.items():
            conf_list.append({'name': key, 'value': val})
        fields = ['name', 'value']

        with open(self.JOT_DIR / 'config.csv', 'w') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames = fields)
            writer.writeheader()
            writer.writerows(conf_list)

    def style_parser(self, color = 15, style = 0):
        return '\x1b[' + str(style) + ';38;5;' + str(color) + 'm'

    def connect(self):
        undefined_db = not self.DB.exists()
        if undefined_db:
            print(f"creating new database: {self.DB}")
            self.conn = sqlite3.connect(self.DB)
            self.cursor = self.conn.cursor()
            sql_file = open(self.SRC_DIR / "create_db.sql")
            sql_as_string = sql_file.read()
            self.cursor.executescript(sql_as_string)
            self.conn.commit()
        else:
            try:
                self.conn = sqlite3.connect(self.DB)
                self.cursor = self.conn.cursor()
            # RSD TODO: Should explicitly catch exceptions
            except:
                print ('attempting to connect to ' + str(self.JOT_DIR))
                sys.exit("Connection to sqlite db failed!")

    def set_db_dir(self, path):
        if os.path.exists(path):
            self.config['db_dir'] = path
        elif path == 'pwd':
            self.config['db_dir'] = os.getcwd()
        else:
            print('database directory not found')
        self.write_config(self.config)
        self.read_config()

    def set_db_name(self, name):
        name = name + '.sqlite'
        self.config['db_name'] = name
        self.write_config(self.config)
        self.read_config()

    def flatten2set(self, object):
        gather = []
        for item in object:
            if isinstance(item, (list, tuple, set)):
                gather.extend(self.flatten2set(item))
            else:
                gather.append(item)
        return set(gather)

    def flatten2list(self, object):
        gather = []
        for item in object:
            if isinstance(item, (list, tuple, set)):
                gather.extend(self.flatten2list(item))
            else:
                gather.append(item)
        return list(gather)

    def gen_symbol(self, gen):
        if gen == 0:
            return ['']
        elif gen == 1:
            return ['>'.ljust(gen, '>') + ' ']
        elif gen > 1:
            return ['>'.rjust(gen, '-') + ' ']
        elif gen == -1:
            return ['? ']

    def smart_wrap(self, text, width):
        text_list = text.split('\n')
        if not isinstance(text_list, list):
            text_list = [text_list]
        wrap = []
        for line in text_list:
            indent = len(line) - len(line.lstrip())
            n = width - indent
            line = line[indent:]
            wrap.append('\n'.join([(''.ljust(indent if i == 0 else indent + 2) + line[i:i+n]) for i in range(0, len(line), n)]))
        return '\n'.join(wrap)

    def print_formatted(self, row, gen = 0, find = None, full = False):
        result = self.summary_formatted(row, gen = gen)
        if result:
            print(result)
            if full:
                if len(row[3]) > self.snippet_width:
                    if self.colorize:
                        [print(self.style_parser(self.palette[0], 0) + '| ' + \
                            self.style_parser(self.palette[8], 0) + i.ljust(self.snippet_width + 20) + \
                            self.style_parser(self.palette[0], 0) + '|')
                            for i in self.smart_wrap(row[3], width = self.snippet_width + 20).split('\n')]
                    else:
                        [print('| ' + i.ljust(self.snippet_width + 20) + '|')
                            for i in self.smart_wrap(row[3], width = self.snippet_width + 20).split('\n')]
                print(self.note_line())

            if find:
                wid = self.snippet_width - len(find)
                widh1 = math.ceil(wid/2)
                widh2 = math.floor(wid/2)
                snip = [i for i in row[3].lower().split('\n') if i.find(self.args.find.lower())>=0]
                for line in snip:
                    context = ('~' + line + '~').split(find.lower())
                    if len(line) > wid:
                        context = ('~' + line + '~').split(find.lower())
                        context_wid = [len(i) for i in context][0:2]
                        if sum(context_wid) > wid:
                            if context_wid[0] > widh1 and context_wid[1] > widh2:
                                line = context[0][-widh1:] + find.upper() + context[1][:widh2]
                            elif context_wid[0] > widh1:
                                line = context[0][-(wid-context_wid[1]):] + find.upper() + context[1]
                            else:
                                line = context[0] + find.upper() + context[1][:wid-context_wid[0]]
                    else:
                        line = context[0] + find.upper() + context[1]
                    print(self.colorize_summary('|                     ' + line.ljust(self.snippet_width) + '|'))

    def summary_formatted(self, row, gen = 0):
        gen_parts = self.gen_symbol(gen)
        sts_str = (row[9] if row[9] else '').center(3, '|')
        gen_str = gen_parts[0]

        idWidth = 5
        sym_len = 0
        multiline = '\n' in row[3]
        note_summary = gen_str + row[3].split('\n')[0]
        nslen0 = len(note_summary)
        tooLong = nslen0 > self.snippet_width
        chr_key = ['|', '~', 'v', '&']
        if tooLong and multiline:
            end_chr = 3
        elif tooLong: # and not multiline
            end_chr = 1
        elif multiline: # and not too long
            end_chr = 2
        else:
            end_chr = 0
        note_summary = note_summary[:self.snippet_width].ljust(self.snippet_width) + chr_key[end_chr]
        due_str = (row[2] if row[2] else '').center(10)
        id_str = row[7][:idWidth].rjust(idWidth) if row[7] else str(row[0]).rjust(idWidth)
        note_str = note_summary
        plain_summary = '| ' + due_str + ' ' + sts_str + '' + id_str + ' ' + note_str + ' '
        return(self.colorize_summary(plain_summary, gen, row[8], end_chr))

    def colorize_summary(self, my_str, gen = 0, status_id = 0, trim_key = 0):
        if self.colorize:
            palette = self.palette
            note_col = palette[0:6]
            sty = {}
            sty[0] = self.style_parser(palette[7], 0)
            sty['ind'] = self.style_parser(palette[0] if status_id == 0 else palette[6], 3)
            sty['note'] = self.style_parser(note_col[status_id], 0)
            sty['end'] = self.style_parser(palette[0], 0 if trim_key == 0 else 5)
            sty['date'] = sty['note']
            sty['stat'] = sty['note']
            mydate = sty['date'] + my_str[1:13]
            mystat = sty['stat'] + my_str[13:16]
            myind = sty['ind'] + my_str[16:22]
            gen_start = 22
            gen_stop = 22 + abs(gen)
            mygen = sty['ind'] + my_str[gen_start:gen_stop]
            mynote = sty['note'] + my_str[gen_stop:22+self.snippet_width]
            myend = sty['end'] + my_str[22+self.snippet_width:23+self.snippet_width] + sty[0]
            return(sty['end'] + my_str[0:1] + mydate + mystat + myind + mygen + mynote + myend)
        else:
            return(my_str)

    def search_notes(self, term):
        sql = ''' SELECT notes_id FROM Notes WHERE description LIKE ? '''
        found_id = self.cursor.execute(sql, ('%' + term + '%',)).fetchall()
        found_id = [tuple([i[0] for i in found_id])][0] # list of tuples to tuple for sqlite input format
        return found_id

    def find_children(self, parent, gen):
        sql = ''' SELECT child FROM Nest WHERE parent = ? '''
        children = list(sum(self.cursor.execute(sql, (parent,)).fetchall(), ()))
        nest = [parent, gen, [self.find_children(child, gen+1) for child in children]]
        return nest

    def family_tree(self):
        sql_parents = ' SELECT parent FROM Nest '
        sql_children = ' SELECT child FROM Nest '
        parents = self.flatten2set(self.cursor.execute(sql_parents).fetchall())
        children = self.flatten2set(self.cursor.execute(sql_children).fetchall())
        last_children = children - parents
        parent_children = children - last_children
        first_parents = list(parents - parent_children)
        first_parents.sort()
        tree = list([self.find_children(parents, 1) for parents in first_parents])
        return tree, parent_children

    def note_line(self):
        return self.colorize_summary('+------------+-+-----+' + ''.ljust(self.snippet_width, '-') + '+')

    def note_header(self):
        return self.colorize_summary('|     Date   |?|  ID   Note ' + str(self.DB).rjust(self.snippet_width-7) + ' |')

    def nest_notes(self, my_ids):
        # calculate nesting of items
        tree, parent_children = self.family_tree()
        id_gen = self.flatten2list(tree)
        # filter nested items
        id_gen = [[i, g] for i, g in zip(id_gen[::2], id_gen[1::2]) if i in my_ids]
        id_gen = self.flatten2list(id_gen)
        ids = id_gen[::2]
        gens = id_gen[1::2]
        # add unresolved nested items that are in my_ids
        circular = parent_children - set(ids) & set(my_ids)
        circular = list(circular)
        circular.sort()
        ids.extend(circular)
        gens.extend([-1] * len(circular))
        # add free items that are in my_ids
        free = set(my_ids) - set(ids)
        free = list(free)
        free.sort()
        ids.extend(free)
        gens.extend([0] * len(free))
        return ids, gens

    def print_nested(self, my_ids, find, full=False):
        ids, gens = self.nest_notes(my_ids)
        [self.print_formatted(self.query_row(i), g, find, full) for i, g in zip(ids, gens)]

    def print_flat(self, my_ids, find, full=False):
        my_ids = my_ids if isinstance(my_ids, list) else [my_ids]
        [self.print_formatted(self.query_row(i), 0, find, full) for i in my_ids]

    def print_notes(self, mode = 'nested', status_show = (1,2,3,4,5), find = None, full = False):
        sql = "SELECT notes_id FROM Notes \
        WHERE status_id IN ({seq})".format(seq=','.join(['?']*len(status_show)))
        sql_vars = status_show

        # filter on search term if provided
        if find:
            found = self.search_notes(find)
            if found is not None:
                sql = sql + " AND notes_id IN ({nid})".format(nid=','.join(['?']*len(found)))
                sql_vars = sql_vars + found

        my_ids = list(sum(self.cursor.execute(sql, sql_vars).fetchall(), ()))
        print(self.note_line() + '\n' + self.note_header() + '\n' + self.note_line())
        if mode == 'flat':
            self.print_flat(my_ids, find, full)
        elif mode == 'nested':
            self.print_nested(my_ids, find, full)
        print(self.note_line())

    def display_note(self, note_id):
        print(self.note_line() + '\n' + self.note_header() + '\n' + self.note_line())
        self.print_flat(note_id, find = None, full = True)

    def query_row(self, note_id):
        sql = ''' SELECT * FROM Notes LEFT JOIN Status ON Notes.status_id = Status.status_id WHERE notes_id = ? '''
        self.cursor.execute(sql, (note_id,))
        row = self.cursor.fetchone()
        return(row)

    def print_note(self, note_id, gen = 0):
        row = self.query_row(note_id)
        if not row:
            print('Note does not exist: ' + str(note_id))
        else:
            pydoc.pipepager(
                self.note_line() + '\n' + self.note_header() + '\n' + self.note_line() + \
                '\n' + self.summary_formatted(row, gen) + \
                '\n' + self.note_line() + \
                '\n' + row[3] + \
                '\n\n' + ('created ' + row[4] + ' & modified ' + row[5]).ljust(self.snippet_width + 17, ">").rjust(self.snippet_width + 24, "<") \
                , cmd=self.view_note_cmd)

    # def print_markdown(self, note_id, gen = 0):
    #     row = self.query_row(note_id)
    #     if row:
    #         '## '  + row[
    #         self.summary_formatted(row, gen) + \
    #             '\n' + self.note_line() + \
    #             '\n' + row[3] + \
    #             '\n\n' + ('created ' + row[4] + ' & modified ' + row[5]).ljust(self.snippet_width + 17, ">").rjust(self.snippet_width + 24, "<") \
    #             , cmd=self.view_note_cmd)
    #
    #     gen_parts = self.gen_symbol(gen)
    #     sts_str = (row[9] if row[9] else '').center(3, '|')
    #     gen_str = gen_parts[0]
    #
    #     idWidth = 5
    #     sym_len = 0
    #     multiline = '\n' in row[3]
    #     note_summary = gen_str + row[3].split('\n')[0]
    #     nslen0 = len(note_summary)
    #     tooLong = nslen0 > self.snippet_width
    #     chr_key = ['|', '~', 'v', '&']
    #     if tooLong and multiline:
    #         end_chr = 3
    #     elif tooLong: # and not multiline
    #         end_chr = 1
    #     elif multiline: # and not too long
    #         end_chr = 2
    #     else:
    #         end_chr = 0
    #     note_summary = note_summary[:self.snippet_width].ljust(self.snippet_width) + chr_key[end_chr]
    #     due_str = (row[2] if row[2] else '').center(10)
    #     id_str = row[7][:idWidth].rjust(idWidth) if row[7] else str(row[0]).rjust(idWidth)
    #     note_str = note_summary
    #     plain_summary = '| ' + due_str + ' ' + sts_str + '' + id_str + ' ' + note_str + ' '

    def identifier_to_id(self, note_id):
        id_list = [int(x) for x in note_id if str(x).isdigit()]
        alias_list = [x for x in note_id if not str(x).isdigit()]
        if id_list:
            sql_id_check = "SELECT notes_id FROM Notes WHERE notes_id IN ({id})".format(id=','.join(['?']*len(id_list)))
            self.cursor.execute(sql_id_check, id_list)
            self.conn.commit()
            id_list = list(sum(self.cursor.fetchall(), ()))
        if alias_list:
            sql_alias_check = "SELECT notes_id FROM Notes WHERE alias IN ({alias})".format(alias=','.join(['?']*len(alias_list)))
            self.cursor.execute(sql_alias_check, alias_list)
            self.conn.commit()
            a_ids = list(sum(self.cursor.fetchall(), ()))
            id_list = id_list + a_ids
        id_list.sort()
        return(id_list)

    def remove_note(self, note_id):
        # may need to be expanded to check other tables?
        print('Deleting note_id = ' + str(note_id))
        sql_delete_query = "DELETE FROM Notes where notes_id = ?"
        self.cursor.execute(sql_delete_query, (str(note_id),))
        self.conn.commit()

        sql_parents = "Select parent FROM Nest where child = ?"
        self.cursor.execute(sql_parents, (note_id,))
        self.conn.commit()
        parents = self.cursor.fetchall()
        parents = set(sum(parents, ()))

        sql_orphans = "Select child FROM Nest where parent = ?"
        self.cursor.execute(sql_orphans, (note_id,))
        self.conn.commit()
        orphans = self.cursor.fetchall()
        orphans = set(sum(orphans, ()))

        sql_delete_nest = "DELETE FROM Nest WHERE parent = ? OR child = ?"
        self.cursor.execute(sql_delete_nest, (note_id, note_id))
        self.conn.commit()

        if orphans is not None and parents is not None:
            sql_adopt = 'INSERT INTO Nest (parent, child) VALUES (?, ?)'
            for parent in parents:
                for orphan in orphans:
                    self.cursor.execute(sql_adopt, (parent, orphan))
                    self.conn.commit()
                    print(str(parent) + ' adopted ' + str(orphan))

    def input_note(self, description, status_id, due, priority, alias, note_id, parent_id):
        if len(note_id) > 1 or str(alias).isdigit():
            print("You cannot assign an alias to multiple ids as once; alias cannot be a number")
            alias = None
        sql_alias_check = 'SELECT EXISTS(SELECT 1 FROM Notes WHERE alias = ?);'
        self.cursor.execute(sql_alias_check, (alias,))
        self.conn.commit()
        if str(sum(self.cursor.fetchall(), ())[0]) == "1":
            print("Alias NOT ACCEPTED: '" + alias + "' is already in use")
            alias = None
        elif alias is None:
            print("No Alias Provided")
        else:
            print("Alias '" + alias + "' is accepted")

        longEntryFormat = description == "<long-entry-note>"
        if due == "0001-01-01":
            due = None
        if not note_id:
            self.add_note(description, status_id, due, priority, alias, parent_id, longEntryFormat)
        else:
            for i in note_id:
                self.edit_note(description, status_id, due, priority, alias, int(i), parent_id, longEntryFormat)

    def long_entry_note(self, existingNote):
        f = tempfile.NamedTemporaryFile(mode='w+t', delete=False)
        n = f.name
        f.write(existingNote)
        f.close()
        subprocess.call([self.EDITOR, n])
        with open(n) as f:
            note = f.read()
        return(note.rstrip())

    def nest_parent_child(self, parent, child):
        if parent is not None and child is not None:
            print('parent: ' + str(parent))
            if parent > 0 and child > 0:
                sql_nest = 'INSERT INTO Nest (parent, child) VALUES (?, ?)'
                self.cursor.execute(sql_nest, (parent, child))
                self.conn.commit()
                print('Parent defined as: ' + str(parent))
            elif parent < 0 and child > 0: # remove parent link
                sql_unnest = 'DELETE FROM Nest WHERE parent = ? and child = ?'
                self.cursor.execute(sql_unnest, (abs(parent), child))
                self.conn.commit()
                print('Parent removed ' + str(abs(parent)))
            elif parent == 0 and child > 0: # remove all parents
                sql_unnest = 'DELETE FROM Nest WHERE child = ?'
                self.cursor.execute(sql_unnest, (child,))
                self.conn.commit()
                print('All parents removed from note')


    def add_note(self, description, status_id, due, priority, alias, parent_id, longEntryFormat):
        if not status_id:
            status_id = 1
        if longEntryFormat:
            description = self.long_entry_note('')
        sql = 'INSERT INTO Notes (description, status_id, due, priority, alias) VALUES (?, ?, ?, ?, ?)'
        self.cursor.execute(sql, (description, status_id, due, priority, alias))
        self.conn.commit()
        print('Added note number: ' + str(self.cursor.lastrowid))
        self.nest_parent_child(parent_id, self.cursor.lastrowid)

    def edit_note(self, description, status_id, due, priority, alias, note_id, parent_id, longEntryFormat):
        sql_old = 'SELECT * FROM Notes where notes_id = ?'
        self.cursor.execute(sql_old, (str(note_id),))
        row = self.cursor.fetchone()
        if longEntryFormat:
            description = self.long_entry_note(str(row[3]))
        new_row = (
                row[0],
                status_id if status_id is not None else row[1],
                due if due is not None else row[2],
                description if description is not None else row[3],
                row[4],
                datetime.strftime(datetime.now(), "%Y-%m-%d %H:%M:%S"),
                priority if priority is not None else row[6],
                alias if alias is not None else row[7]
                )
        sql = 'INSERT or REPLACE into Notes VALUES (?, ?, ?, ?, ?, ?, ?, ?)'
        self.cursor.execute(sql, new_row)
        self.conn.commit()
        print('Edited note number: ' + str(self.cursor.lastrowid))
        self.nest_parent_child(parent_id, note_id)

    def valid_date(self, s):
        try:
            return datetime.strftime(datetime.strptime(s, "%Y-%m-%d"), "%Y-%m-%d")
        except ValueError:
            msg = "not a valid date: {0!r}".format(s)
            raise argparse.ArgumentTypeError(msg)

    def parse_inputs(self):
        parser = argparse.ArgumentParser()
        group1 = parser.add_argument_group(title="positional arguments")
        group = parser.add_argument_group(title="item inputs", description="set attributes")
        group23 = parser.add_argument_group(title="manage items")
        group25 = parser.add_argument_group(title="display options")
        group2 = parser.add_argument_group(title="configure JOT")
        group3 = parser.add_argument_group(title="developer tools")
        group1.add_argument("identifier", help="Specify note identifier(s) by index or alias (optional)", nargs='*')
        group.add_argument("-n", "--note", help="Contents of note or blank to initiate editor", nargs='?', const='<long-entry-note>', default=None)
        group.add_argument("-s", "--status", type=int, choices=[1, 2, 3, 4, 5], help="Status: 1 (notes), 2 (to-do), 3 (complete), 4 (cancelled), 5 (partial)", default=None)
        group25.add_argument("-f", "--find", help="Find string within notes")
        group.add_argument("-d", "--date", help="Key Date - format YYYY-MM-DD", type=self.valid_date, nargs='?', const='0001-01-01', default=None)
        group.add_argument("-i", "--priority", nargs='?', const=1, default=None, type=int, help="Prioritize item (priority = 1), or 0 to unprioritize")
        group.add_argument("-a", "--alias", help="Up to 5 character unique alias to replace index", default=None)
        group23.add_argument("-rm", action = "store_true", help="remove item(s)")
        group.add_argument("-p", "--parent", nargs='?', const=0, default=None, type=int, help="Assign parent, 0 or blank to remove all, -id to remove specific id")
        group25.add_argument("-l", "--less", action = 'store_true', help="Display using `less`")
        group25.add_argument("-o", "--order", type=str, choices=['nested', 'flat'], help="Note summary table style", default = 'nested')
        group25.add_argument("-v", "--verbose", action = "store_true", help="Increase output verbosity")
        group2.add_argument("-config", help="Configure JOT preferences", action = "store_true")
        group2.add_argument("-dir", help="set db directory, current working directory if no argument", nargs='?', default=None, const='pwd')
        group2.add_argument("-dbname", help="set db name to supplied argument (filename excluding `.sqlite` extension) or jot (default) if none", nargs='?', const='jot', default=None)
        group3.add_argument("-code", action = "store_true", help="Open python code for development")
        group3.add_argument("-readme", action = "store_true", help="Open README.md for editing")
        group3.add_argument("-sqlite", action = "store_true", help="Open create.sqlite for editing")
        args = parser.parse_args()
        self.args = args if args else ''

#    def input_logic(self):
#        args = self.args
#        if args.identifier:
#            if len(args.identifier) == 1:
#                if args.status or args.date or args.priority or args.alias or args.parent:
#                    # input note changes
#            else:
#                if (args.status or args.date or args.priority or args.parent) and not args.alias:
#                    # input note changes
#                else:
#                    print("Use -s -d -i or -p but not -a when editing multiple items")

    def main(self):
        args = self.args
        # Set Preferences
        if args.dir and args.dbname:
            self.set_db_dir(args.dir)
            self.set_db_name(args.dbname)
            self.connect()
        elif args.dir:
            self.set_db_dir(args.dir)
            self.connect()
        elif args.dbname:
            self.set_db_name(args.dbname)
            self.connect()
        # Input
        if args.code or args.readme or args.sqlite or args.config:
            if args.code:
                subprocess.call([self.EDITOR, self.SRC_DIR / 'jot.py'])
            if args.config:
                subprocess.call([self.EDITOR, self.JOT_DIR / 'config.csv'])
            if args.readme:
                subprocess.call([self.EDITOR, self.SRC_DIR.parent / 'README.md'])
            if args.sqlite:
                subprocess.call([self.EDITOR, self.SRC_DIR / 'create_db.sql'])
        elif args.note or (args.identifier and (args.status or args.date or args.priority or args.alias or args.parent)):
            self.input_note(description=args.note, status_id=args.status, due=args.date, priority=args.priority, alias=args.alias[:5] if args.alias else None, note_id=self.identifier_to_id(args.identifier), parent_id=args.parent)
        elif args.rm:
            [self.remove_note(i) for i in self.identifier_to_id(args.identifier)]
        # Output
        if args.less:
            [self.print_note(i) for i in self.identifier_to_id(args.identifier)]
        elif args.verbose:
            self.print_notes(mode = args.order, status_show = (1,2,3,4,5), find = args.find, full = True)
        elif args.identifier:
            self.display_note(self.identifier_to_id(args.identifier))
        else: # if no options, show active notes
            self.print_notes(mode = args.order, status_show = (1,2,5), find = args.find)


def main():
    Jot()

if __name__ == "__main__":
    main()

# def convertToBinaryData(filename):
#     # Convert digital data to binary format
#     with open(filename, 'rb') as file:
#         blobData = file.read()
#     return blobData
#

# def insertBLOB(empId, name, photo, resumeFile):
#     try:
#         sqliteConnection = sqlite3.connect(DB)
#         cursor = sqliteConnection.cursor()
#         print("Connected to SQLite")
#         sqlite_insert_blob_query = """ INSERT INTO Files
#                                   (id, name, photo, resume) VALUES (?, ?, ?, ?)"""
#
#         empPhoto = convertToBinaryData(photo)
#         resume = convertToBinaryData(resumeFile)
#         # Convert data into tuple format
#         data_tuple = (empId, name, empPhoto, resume)
#         cursor.execute(sqlite_insert_blob_query, data_tuple)
#         sqliteConnection.commit()
#         print("Image and file inserted successfully as a BLOB into a table")
#         cursor.close()
#
#     except sqlite3.Error as error:
#         print("Failed to insert blob data into sqlite table", error)
#     finally:
#         if sqliteConnection:
#             sqliteConnection.close()
#             print("the sqlite connection is closed")
#
# insertBLOB(1, "Smith", "E:\pynative\Python\photos\smith.jpg", "E:\pynative\Python\photos\smith_resume.txt")
# insertBLOB(2, "David", "E:\pynative\Python\photos\david.jpg", "E:\pynative\Python\photos\david_resume.txt")
