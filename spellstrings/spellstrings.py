#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import division

from cStringIO import StringIO
from datetime import timedelta
from decimal import Decimal
from math import ceil, floor

import re

from .paperdoll import Paperdoll


def case_insensitive(lower):
	upper = [k.upper() for k in lower]
	lower.extend(upper)


paperdolldict = {
	"ap":   "ATTACK_POWER",
	"ar":   "ARMOR",
	"bc2":  "PERCENT_BC2",
	"bh":   "BONUS_HEALING",
	"hnd":  "MAIN_WPN_HANDS",
	"mw":   "MAIN_WPN_DMG",
	"mwb":  "MAIN_WPN_BASEDMG",
	"mws":  "MAIN_WPN_SPEED",
	"pa":   "PERCENT_ARCANE",
	"pfi":  "PERCENT_FIRE",
	"pfr":  "PERCENT_FROST",
	"ph":   "PERCENT_HOLY",
	"pn":   "PERCENT_NATURE",
	"ps":   "PERCENT_SHADOW",
	"pbh":  "PERCENT_BONUS_HEALING",
	"pbhd": "PERCENT_BONUS_HEALING_DAMAGE",
	"pl":   "PLAYER_LVL",
	"rap":  "RANGED_ATTACK_POWER",
	"rwb":  "RANGED_WPN_BASEDMG",
	"sp":   "SPELL_POWER",
	"spa":  "SPELL_POWER_ARCANE",
	"spfi": "SPELL_POWER_FIRE",
	"spfr": "SPELL_POWER_FROST",
	"sph":  "SPELL_POWER_HOLY",
	"spi":  "SPIRIT",
	"spn":  "SPELL_POWER_NATURE",
	"sps":  "SPELL_POWER_SHADOW",	
}
paperdolls = paperdolldict.keys()
case_insensitive(paperdolls)
paperdolls.sort(key=lambda i: i + "\xff\xff\xff\xff") # pbhd needs to come before pbh, so on
paperdolls_s = "|".join(paperdolls)

booleans = "Ggl"
functions = ["ceil", "cond", "eq", "floor", "gt", "max", "min"]
case_insensitive(functions)
macros = "ADFMRSabderfhimnoqrstuvxz"
functions_s = "|".join(functions)
macros_s = "|".join(macros)

sre_function = re.compile(r"(%s)\(([^,]+),([^,)]+),?([^)]?)\)" % "|".join(functions)) # cond|eq|max|min(arg1, arg2[, arg3])
# (cond|eq|max|min) # NO EMBEDDED FUNCTION SUPPORT
# \(                # opening parenthese
#   ([^,]+),        # grab anything except a "," followed by a ","
#   ([^,)]+)        # grab anything except ",)"
#         ,?        # followed by , (optional if third arg exists)
#   ([^)]?)         # grab anything but a parenthese (optional)
# \)                # closing parenthese

sre_boolean = re.compile(r"(%s)([^:]+):([^;]+);" % "|".join(booleans)) # g|lFirst String:Second String;
sre_braces = re.compile(r"\{([^}]+)\}\.?(\d+)?") # ${} not supported
sre_operator = re.compile(r"[*/](\d+);(\d*)(%s)([123]?)" % macros_s) # /1000;54055o2
sre_macro = re.compile(r"(\d*)(%s)([123]?)" % macros_s)
sre_paperdoll = re.compile(r"(%s)" % paperdolls_s)
sre_variable = re.compile(r"<([A-Za-z0-9]+)>")
sre_variable_dbc = re.compile(r"^\$([A-Za-z0-9]+)=(.+)$")

class WSMLSyntaxError(SyntaxError):
	pass


def parse_sdv(file):
	"Parse a SpellDescriptionVariables.dbc file, return a dict"
	ret = {}
	for row in file:
		_row = {}
		for variable in file[row].variables.split():
			sre = sre_variable_dbc.search(variable)
			k, v = sre.groups()
			_row[k] = v
		ret[file[row]._id] = _row
	return ret

def getarglist(obj):
	"Finds arguments given to a function"
	parens = 1
	values = []
	buffer = ""
	for c in obj:
		if c == "(":
			parens += 1
		elif c == ")":
			parens -= 1
		elif c == "," and parens == 1:
			values.append(buffer)
			buffer = ""
			continue
		if parens == 0:
			values.append(buffer)
			return values
		buffer += c
	
	raise WSMLSyntaxError("Expected closing ')' on string %r" % (obj))

def get_braced(string):
	"Get calculation values from braces"
	braces = 1
	ret = []
	c = string.read(1)
	while True:
		c = string.read(1)
		if c == "{":
			braces += 1
		elif c == "}":
			braces -= 1
			if not braces:
				return "".join(ret)
		ret.append(c)
	
	string.seek(0)
	raise WSMLSyntaxError("Expected closing '}' on string %r" % (string.read()))

def parse_conditional_args(string):
	"TODO make use of if/elif"
	c = string.read(1)
	
	while c == " ": # ignore whitespace
		c = string.read(1)
	
	if c == "$": # Weird.
		c = string.read(1)
	
	if c == "?": # "elif"
		cond_elif = parse_conditional_id(string)
		arg_elif = parse_brackets(string)
		return parse_conditional_args(string)
	
	elif c == "[":
		arg_else = parse_brackets(string)
		return arg_else
	
	raise WSMLSyntaxError("Expected opening '[' for else condition on string %r (got %r instead)" % (string.read(), c))

def parse_conditional_id(string):
	"TODO (s25306|!((!a48165)|a66109)) == s25306 or not (not a48165 or a66109)"
	ret = []
	c = string.read(1)
	while c != "[":
		ret.append(c)
		c = string.read(1)
	return "".join(ret)

def parse_brackets(string):
	"Get the next brackets in a StringIO"
	brackets = 1
	ret = []
	while True:
		c = string.read(1)
		if c == "[":
			brackets += 1
		elif c == "]":
			brackets -= 1
			if not brackets:
				return "".join(ret)
		ret.append(c)
	
	string.seek(0)
	raise WSMLSyntaxError("Expected closing ']' on string %r" % (string.read()))

class Duration(timedelta):
	def __str__(self):
		if self == timedelta(milliseconds=0):
			return "until cancelled"
		elif self < timedelta(minutes=1):
			return "%d sec" % self.seconds
		elif self < timedelta(hours=1):
			return "%d min" % (self.seconds / 60)
		elif self == timedelta(hours=1):
			return "%d hour" % (self.seconds / 3600)
		elif self < timedelta(days=1):
			return "%d hrs" % (self.seconds / 3600)
		else:
			return "%d days" % self.days


class Range(Decimal): # used in $s
	def __init__(self, start, stop):
		Decimal.__init__(self)
		self.start = Decimal(abs(start))
		self.stop = Decimal(abs(stop))
	
	def __str__(self):
		if self.stop > self.start:
			return "%i to %i" % (self.start, self.stop)
		
		return "%i" % (self.start)
	
	def __mul__(self, mul):
		mul = Decimal(str(mul))
		self.start *= mul
		self.stop *= mul
		return Decimal.__mul__(self, mul)
	
	def __div__(self, div):
		div = Decimal(str(div))
		self.start /= div
		self.stop /= div
		return Decimal.__div__(self, div)


class HtmlValue(object): # XXX
	def __init__(self, value, tag="a", href=None, classes=[]):
		self.value = value
		self.tag = tag
		self.href = href and ' href="%s"' % (href) or ""
		self.classes = classes and ' class="%s"' % (" ".join(classes)) or ""
	
	def __str__(self):
		if not self.tag:
			return str(self.value)
		return """<%(tag)s%(href)s%(classes)s>%(value)s</%(tag)s>""" % (self.__dict__)


class LearnedValue(object): # XXX
	def __init__(self, id, spell, arg1, arg2):
		self.args = [
			str(HtmlValue(arg1, tag="span", classes=["learned-s1"])),
			str(HtmlValue(arg2, tag="span", classes=["learned-s2"])),
		]
		self.id = id
		self.spell = spell
	
	def __str__(self):
		return ' <a href="/s/%i/" class="learned-s">&lt;%s&gt;</a>%s' % (self.id, self.spell, "".join(self.args))


SPELL_DESCRIPTION_VARIABLES = {}
class SpellString(object):
	def __init__(self, string):
		self.string = string
		self.reset()
	
	def reset(self):
		self.row = None
		self.env = None
		self.file = None
		self.paperdoll = None
		self.last = 0
		self.object = [""]
		self.count = 0
		self.pos = 0
		self.variables = {}
	
	
	def __str__(self):
		return self.string
	
	def __repr__(self):
		return self.string.__repr__()
	
	
	def appendchr(self):
		self.object[self.count] += self.string[self.pos]
	
	def appendvar(self, var):
		self.count += 1
		self.object.append(var)
		self.count += 1
		self.object.append("")
	
	
	def checkfmt(self):
		string = self.string[self.pos:]
		char = string[0]
		if char == "{":
			return self.fmt_braced()
		elif char == "?":
			return self.fmt_conditional()
		elif char == "/":
			return self.fmt_divisor()
		elif char == "*":
			return self.fmt_multiplicator()
		elif char.isdigit():
			return self.fmt_macro()
		else:
			return self.checkvar()
	
	def checkvar(self):
		"Checks whether value is a function, paperdoll or macro"
		string = self.string[self.pos:]
		
		is_function = sre_function.match(string)
		is_paperdoll = sre_paperdoll.match(string)
		is_macro = sre_macro.match(string)
		is_boolean = sre_boolean.match(string)
		
		if is_function:
			return self.fmt_function()
		elif is_paperdoll:
			return self.fmt_paperdoll()
		elif is_macro:
			return self.fmt_macro()
		elif is_boolean:
			return self.fmt_boolean()
	
	
	def expand(self):
		"Expands self.object into a string"
		s = ""
		for k in self.object:
			s += str(k)
		return s
	
	def get_macro(self, char, spell, effect):
		if not hasattr(self, "macro_%s" % char):
			char = char.lower()
		return getattr(self, "macro_%s" % char)(spell, effect)
	
	def get_variable(self, var):
		global SPELL_DESCRIPTION_VARIABLES
		if not SPELL_DESCRIPTION_VARIABLES: # Cache the dbc
			SPELL_DESCRIPTION_VARIABLES = parse_sdv(self.env["spelldescriptionvariables"])
		i = int(self.row.descriptionvars) #descriptionvars id
		row = SPELL_DESCRIPTION_VARIABLES[i]
		return row[var]
	
	def fmt_boolean(self):
		string = self.string[self.pos:]
		sre = sre_boolean.search(string)
		char, arg1, arg2 = sre.groups()
		self.pos += len(sre.group())
		self.appendvar(getattr(self, "boolean_%s" % char)(arg1, arg2))
	
	def fmt_braced(self):
		"""
		s58644:10147
		${58644m1/-10} => -5864
		"""
		_string = self.string[self.pos:]
		string = StringIO(str(_string))
		calc = get_braced(string)
		self.pos += string.tell()
		if string.read(1) == ".":
			decimals = []
			c = string.read(1)
			while c.isdigit():
				decimals.append(c)
				c = string.read(1)
			self.pos += len(decimals) + 1 # additional dot
			decimals = int("".join(decimals or ["0"]))
		else:
			decimals = 0
		val = SpellString(calc).format(self.row, self.paperdoll)
		format = "%%.%if" % (decimals)
		try:
			val = eval(val)
			val = format % abs(val)
		except Exception:
			val = str(val)
		self.appendvar(val)
	
	def fmt_divisor(self):
		string = self.string[self.pos:]
		sre = sre_operator.match(string)
		if not sre: # 71182 @ 10571
			return self.appendvar("$")
		amount, spell, char, effect = sre.groups()
		spell = spell and int(spell) or self.row._id
		effect = effect and int(effect) or 1
		if spell not in self.file:
			self.pos += len(sre.group())
			return self.appendvar("$%s%i" % (char, effect))
		val = self.get_macro(char, spell, effect)
		val = val / Decimal(amount)
		self.pos += len(sre.group())
		self.appendvar(val)
	
	def fmt_multiplicator(self):
		string = self.string[self.pos:]
		sre = sre_operator.match(string)
		amount, spell, char, effect = sre.groups()
		spell = spell and int(spell) or self.row._id
		effect = effect and int(effect) or 1
		if spell not in self.file:
			self.pos += len(sre.group())
			return self.appendvar("$%s%i" % (char, effect))
		val = self.get_macro(char, spell, effect)
		val = val * int(amount)
		self.pos += len(sre.group())
		self.appendvar(val)
	
	def fmt_function(self):
		"Function call (1-3 args)"
		string = self.string[self.pos:]
		if re.search(r"\$(%s)\(" % functions_s, string[2:]): # nested function call
			func = string.split("(")[0]
			args = getarglist(string[len(func)+1:]) # we don't want the opening (
			self.pos += len("%s(%s)" % (func, ",".join(args)))
			args.extend([None, None]) # FIXME We really shouldn't hardcode the amount of args
			arg1, arg2, arg3 = args[:3]
		else:
			sre = sre_function.match(string)
			func, arg1, arg2, arg3 = sre.groups()
			self.pos += len(sre.group())
		
		self.appendvar(getattr(self, "function_%s" % (func.lower()))(arg1, arg2, arg3))
	
	def fmt_conditional(self):
		_string = self.string[self.pos:]
		string = StringIO(str(_string))
		string.read(1) # "?"
		cond_if = parse_conditional_id(string)
		arg_if = parse_brackets(string)
		arg_else = parse_conditional_args(string)
		arg_else = SpellString(arg_else).format(self.row, self.paperdoll)
		
		self.pos += string.tell()
		self.appendvar(arg_else)
	
	def fmt_macro(self):
		string = self.string[self.pos:]
		sre = sre_macro.match(string)
		if not sre: # FIXME 3826
			return self.appendvar("$")
		spell, char, effect = sre.groups()
		self.pos += len(sre.group())
		spell = spell and int(spell) or self.row._id
		if spell not in self.file:
			return self.appendvar("$" + char + effect)
		effect = effect and int(effect) or 1
		val = self.get_macro(char, spell, effect)
		self.appendvar(val)
	
	def fmt_paperdoll(self):
		string = self.string[self.pos:]
		sre = sre_paperdoll.match(string)
		var = sre.group(1)
		self.pos += len(sre.group())
		self.appendvar(self.assign_paperdoll(var.lower()))
	
	
	def boolean_G(self, male, female):
		"Redirect to boolean_g"
		return self.boolean_g(male, female)
	
	def boolean_g(self, male, female):
		"Player gender"
		gender = self.paperdoll["GENDER"]
#		if gender not in (0, 1):
#			return "[%s/%s]" % (male, female)
		return (male, female)[gender]
	
	def boolean_l(self, singular, plural):
		"Pluralization by last value"
		if int(self.last) == 1:
			return singular
		return plural
	
	def assign_paperdoll(self, var):
		p = self.paperdoll[paperdolldict[var]]
		try:
			int(p)
		except ValueError:
			return var.upper()
	
	def function_floor(self, arg1, arg2=None, arg3=None):
		"Return the ceil of a float"
		arg1 = SpellString(arg1).format(self.row, self.paperdoll)
		
		try:
			arg1 = float(arg1)
		except ValueError:
			return "ceil(%s)" % (arg1)
		
		return ceil(arg1)
	
	def function_cond(self, arg1, arg2, arg3):
		"Return value depending on condition"
		arg1 = SpellString(arg1).format(self.row, self.paperdoll)
		arg2 = SpellString(arg2).format(self.row, self.paperdoll)
		arg3 = SpellString(arg3).format(self.row, self.paperdoll)
		
		if arg1: # XXX
			return arg2
		
		return arg3
	
	def function_eq(self, arg1, arg2, arg3=None):
		"Return true if args are equal"
		arg1 = SpellString(arg1).format(self.row, self.paperdoll)
		arg2 = SpellString(arg2).format(self.row, self.paperdoll)
		
		if arg1 == arg2:
			return True
		
		return False
	
	def function_floor(self, arg1, arg2=None, arg3=None):
		"Return the floor of a float"
		arg1 = SpellString(arg1).format(self.row, self.paperdoll)
		
		try:
			arg1 = float(arg1)
		except ValueError:
			return "floor(%s)" % (arg1)
		
		return floor(arg1)
	
	def function_gt(self, arg1, arg2, arg3=None):
		"Return true if arg1 > arg2"
		arg1 = SpellString(arg1).format(self.row, self.paperdoll)
		arg2 = SpellString(arg2).format(self.row, self.paperdoll)
		
		try:
			arg1, arg2 = int(arg1), int(arg2)
		except ValueError:
			return "[Greater than: %s, %s]" % (arg1, arg2)
		
		return arg1 > arg2 and True or False
	
	def function_max(self, arg1, arg2, arg3=None):
		"Return highest value"
		arg1 = SpellString(arg1).format(self.row, self.paperdoll)
		arg2 = SpellString(arg2).format(self.row, self.paperdoll)
		
		try:
			arg1, arg2 = int(arg1), int(arg2)
		except ValueError:
			return "max(%s, %s)" % (arg1, arg2)
		return arg1 > arg2 and arg1 or arg2
	
	def function_min(self, arg1, arg2, arg3=None):
		"Return lowest value"
		arg1 = SpellString(arg1).format(self.row, self.paperdoll)
		arg2 = SpellString(arg2).format(self.row, self.paperdoll)
		
		try:
			arg1, arg2 = int(arg1), int(arg2)
		except ValueError:
			return "min(%s, %s)" % (arg1, arg2)
		return arg1 < arg2 and arg1 or arg2
	
	
	def macro_a(self, spell, effect):
		"Spelleffect radius"
		row = getattr(self.file[spell], "radius_effect_%i" % (effect))
		val = row and row[1] or 0
		return "%.0f" % val
	
	def macro_b(self, spell, effect):
		"Spelleffect proc chance"
		val = getattr(self.file[spell], "points_combo_effect_%i" % (effect))
		self.last = val
		return "%.0f" % val
	
	def macro_d(self, spell, effect=0):
		"Spell duration"
		row = getattr(self.file[spell], "duration")
		val = row and row[1] or 0
		return Duration(milliseconds=val)
	
	def macro_e(self, spell, effect):
		"Spelleffect proc value"
		val = getattr(self.file[spell], "amplitude_effect_%i" % (effect))
		self.last = val
		return val
	
	def macro_f(self, spell, effect):
		"Spelleffect finisher coefficient"
		val = getattr(self.file[spell], "chain_amplitude_effect_%i" % (effect))
		self.last = val
		return "%.0f" % val
	
	def macro_h(self, spell, effect=0):
		"Spell proc chance"
		val = getattr(self.file[spell], "proc_chance")
		self.last = val
		return val
	
	def macro_i(self, spell, effect=0):
		"Spell max targets"
		val = getattr(self.file[spell], "max_targets")
		self.last = val
		return val
	
	def macro_M(self, spell, effect):
		"Spelleffect max damage"
		val = getattr(self.file[spell], "damage_base_effect_%i" % (effect))
		sides = getattr(self.file[spell], "die_sides_effect_%i" % (effect))
		dice = getattr(self.file[spell], "dice_base_effect_%i" % (effect))
		val = val + (sides*dice)
		self.last = val
		return val
	
	def macro_m(self, spell, effect):
		"Spelleffect min damage"
		#calc = "${$e%(effect)i+(1*(%i+(%i+($PL-%i))))+(%i*($PL-%i))}"
		#val = SpellString(calc)
		val = abs(getattr(self.file[spell], "damage_base_effect_%i" % (effect)) + 1)
		self.last = val
		return val
	
	def macro_n(self, spell, effect=0):
		"Spell proc charges"
		val = getattr(self.file[spell], "proc_charges")
		self.last = val
		return val
	
	def macro_o(self, spell, effect):
		"Spelleffect damage over time"
		val = getattr(self.file[spell], "duration")
		if not val:
			return 0
		s = self.macro_s(spell, effect)
		d = val[1]
		t = getattr(self.file[spell], "aura_interval_effect_%i" % (effect)) or 5000
		t = Decimal(t)
		val = d/t*s
		return val
	
	def macro_q(self, spell, effect):
		"Spelleffect misc value"
		val = getattr(self.file[spell], "misc_value_1_effect_%i" % (effect))
		self.last = val
		return val
	
	def macro_R(self, spell, effect=0):
		"Spell range friendly"
		val = getattr(self.file[spell], "range").range_max_friendly
		self.last = val
		return "%.0f" % val
	
	def macro_r(self, spell, effect):
		"Spell range enemy"
		val = getattr(self.file[spell], "range").range_max
		self.last = val
		return "%.0f" % val
	
	def macro_s(self, spell, effect):
		"Spelleffect damage range"
		m = self.macro_m(spell, effect)
		M = self.macro_M(spell, effect)
		val = Range(m, M)
		self.last = val
		return val
	
	def macro_t(self, spell, effect):
		"Spelleffect time interval"
		val = getattr(self.file[spell], "aura_interval_effect_%i" % (effect)) / 1000
		self.last = val
		return val
	
	def macro_u(self, spell, effect=0):
		"Spell stack"
		val = getattr(self.file[spell], "stack")
		self.last = val
		return val
	
	def macro_v(self, spell, effect=0):
		"Spell target level restrictions"
		val = getattr(self.file[spell], "max_target_level")
		self.last = val
		return val
	
	def macro_x(self, spell, effect):
		"Spelleffect chain targets"
		val = getattr(self.file[spell], "chain_targets_effect_%i" % (effect))
		self.last = val
		return val
	
	def macro_z(self, spell=0, effect=0):
		"Player home"
		return self.paperdoll["HOME"]
	
	
	def format(self, row, paperdoll=Paperdoll()):
		self.row = row
		self.file = self.row._parent
		self.env = self.row._parent.environment
		self.paperdoll = paperdoll
		string = self.string
		
		if not string.count("$"): # No variables in the string
			self.pos = len(string)
			self.object[0] = string
		else:
			sre = sre_variable.search(string)
			while sre:
				var, = sre.groups()
				_var = self.get_variable(var)
				string = string[:sre.start()-1] + _var + string[sre.end():]
				sre = sre_variable.search(string)
			self.string = string
		
		while self.pos < len(string):
			if string[self.pos] == "$":
				self.pos += 1
				try:
					self.checkfmt()
				except NotImplementedError:
					raise
			else:
				self.appendchr()
				self.pos += 1
		
		val = self.expand()
		self.reset()
		return val