'''
Provides automatic migration of JSON files when the underlying "shema" changes.

Copyright 2016 Raytheon BBN Technologies

Original author: Brian Donovan
'''

import json
import itertools

# Migrates json file versions using a version number
# File version prior to adding a version number are 0
# Version 1 adds the version to all json files
# Version 2+ change the structure of the files

# to add migrations add version_{n}_to_{n+1} methods in the subclasses of JSONMigrator
# currently  [IntrumentMigrator, ChannelMigrator,SweepMigrator, MeasurementMigrator]
# to make the changes in the json dict

class JSONMigrator(object):
	""" Base class for the JSON Migration

		Includes the base method for migrating
		Assumes migration methods are of the form version_{n}_to_{n+1}

		Includes version_0_to_1
	"""

	def __init__(self, fileName, libraryClass, primaryKey, max_version = 1):
		self.fileName = fileName
		self.jsonDict = None
		self.min_version = 0
		self.max_version = max_version
		self.primaryKey = primaryKey
		self.primaryDict = None
		self.libraryClass = libraryClass

	def version(self):
		try:
			return self.jsonDict['version']
		except:
			return 0

	def load(self):
		try:
			with open(self.fileName, 'r') as FID:
			    self.jsonDict = json.load(FID)
		except IOError:
			print('json file {0} not found'.format(self.fileName))
			self.jsonDict = None

		if not self.json_input_validate():
			self.jsonDict = None
			return

		# cache primary dictionary
		self.primaryDict = self.jsonDict[self.primaryKey]

	def json_input_validate(self):
		if not self.is_class(self.jsonDict, self.libraryClass) or self.primaryKey  not in self.jsonDict:
			print("Error json file is not a {0}".format(self.libraryClass))
			return False
		return True

	def is_class(self, jsonDict, searchClasses):

		if type(searchClasses) == type(''):
			searchClasses = [searchClasses]

		if type(jsonDict) != type({}):
			return False

		if 'x__class__' not in jsonDict.keys():
			return False

		for className in searchClasses:
			if jsonDict['x__class__'] == className:
				return True

		return False

	def save(self):
		# store primary dictionary back into json dictionary
		self.jsonDict[self.primaryKey] = self.primaryDict

		# write out file
		with open(self.fileName,'w') as FID:
			json.dump(self.jsonDict, FID, indent=2, sort_keys=True)

	def migrate(self):
		messages = []
		self.load()
		if self.jsonDict:
			while self.version() < self.max_version:
				migrate_function = "version_{0}_to_{1}".format(self.version(), self.version() + 1)
				msg = "Migrating: {0}.{1}()".format(self.__class__.__name__, migrate_function)
				messages.append(msg)
				function = getattr(self,migrate_function)
				function()
				self.jsonDict['version'] = self.version() + 1
			self.save()
		return messages

	def get_items_matching_class(self, classes):
		return [a for a in self.primaryDict if self.is_class(self.primaryDict[a],classes)]

	def version_0_to_1(self):
		# does nothing but bump version number
		pass

class IntrumentMigrator(JSONMigrator):
	""" Migrator for the Intrument Manager JSON File """
	def __init__(self, filename):
		super(IntrumentMigrator, self).__init__(
			filename,
			"InstrumentLibrary",
			"instrDict",
			3)

	def version_1_to_2(self):

		# Migration step 1
		# Change Labbrick64 class to Labbrick

		chClasses = ['Labbrick64']
		lb64 = self.get_items_matching_class(chClasses)

		for lb in lb64:
			self.primaryDict[lb]['x__class__'] = "Labbrick"

	def version_2_to_3(self):
		# Migration step 2
		# Follow X6 channel schema change
		scopes = self.get_items_matching_class(['X6'])
		for x6 in scopes:
			for channel in self.primaryDict[x6]['channels'].values():
				channel['enableDemodResultStream'] = channel['enableResultStream']
				channel['enableRawResultStream'] = channel['enableResultStream']
				channel['demodKernel'] = channel['kernel']
				channel['rawKernel'] = ''
				del channel['enableResultStream']
				del channel['kernel']

class ChannelMigrator(JSONMigrator):
	""" Migrator for the Channel Manager JSON File """
	def __init__(self, filename):
		super(ChannelMigrator, self).__init__(
			filename,
			'ChannelLibrary',
			'channelDict',
			5)

	def version_1_to_2(self):

		# Migration step 1
		# Move SSBFreq from Physical Channel for Qubits to the Logical Qubit Channel

		# two phases
		# 1) copy all of the data from physical channel
		# 2) delete data after copying is done in cases there are many-to-one mappings
		lcClasses = ['Qubit', 'Measurement']
		logicalChannels = self.get_items_matching_class(lcClasses)

		for lc in logicalChannels:
			pc = self.primaryDict[lc]['physChan']
			if pc not in self.primaryDict:
				print('Error: Physical Channel {0} not found.'.format(pc))
				continue
			if 'SSBFreq' not in self.primaryDict[pc]:
				print("Warning: did not find SSBFreq for PhysicalChannel: {0}".format(pc))
				continue
			frequency = self.primaryDict[pc]['SSBFreq']
			self.primaryDict[lc]['frequency'] = frequency

		lcClasses = ['PhysicalQuadratureChannel']
		iqChannels = self.get_items_matching_class(lcClasses)

		for iq in iqChannels:
			if 'SSBFreq' not in self.primaryDict[iq]:
				continue
			del self.primaryDict[iq]['SSBFreq']

	def version_2_to_3(self):
		#Migration step 2
		#Set default digitizer trigger to digitizerTrig
		measChannels = self.get_items_matching_class('Measurement')

		for mc in measChannels:
			if 'trigChan' in self.primaryDict[mc]:
				if self.primaryDict[mc]['trigChan'] != '':
					continue
			self.primaryDict[mc]['trigChan'] = 'digitizerTrig'

	def version_3_to_4(self):
		self.jsonDict['x__module__'] = 'QGL.ChannelLibrary'
		print("""
	PhysicalChannels have a new 'translator' attribute which must be updated for
	compile_to_hardware to work. Please choose the instrument type for the
	following AWGs.
""")
		AWGs = set()
		physChans = self.get_items_matching_class(['PhysicalQuadratureChannel', 'PhysicalMarkerChannel'])
		for name in physChans:
			ch = self.primaryDict[name]
			if ch['AWG']:
				AWGs.add(ch['AWG'])
		awgmap = {}
		for awg in AWGs:
			response = input('Type for "{0}" (1: APS1, 2: APS2, or 3: Tek5014): '.format(awg))
			responsemap = {'1': 'APSPattern', '2': 'APS2Pattern', '3': 'TekPattern'}
			if response not in responsemap.keys():
				raise NameError('Invalid response: "%s" not one of %s' % (response, responsemap.keys()))
			awgmap[awg] = responsemap[response]
		for name in physChans:
			ch = self.primaryDict[name]
			ch['translator'] = awgmap[ch['AWG']]

	def version_4_to_5(self):
		# 'AWG' property of PhysicalChannels renamed to 'instrument'
		physChans = self.get_items_matching_class(['PhysicalQuadratureChannel', 'PhysicalMarkerChannel'])

		for name in physChans:
			ch = self.primaryDict[name]
			ch['instrument'] = ch['AWG']
			del ch['AWG']

class SweepMigrator(JSONMigrator):
	""" Migrator for the Sweeps JSON File """

	def __init__(self, filename):
		super(SweepMigrator, self).__init__(
			filename,
			"SweepLibrary",
			"sweepDict",
			1)

class MeasurementMigrator(JSONMigrator):
	""" Migrator for the Sweeps JSON File """

	def __init__(self, filename):
		super(MeasurementMigrator, self).__init__(
			filename,
			"MeasFilterLibrary",
			"filterDict",
			1)

def migrate_all(config):
	migrators = [IntrumentMigrator,
	             SweepMigrator,
	             MeasurementMigrator]
	configFiles = [config.instrumentLibFile,
				   config.sweepLibFile,
				   config.measurementLibFile]
	messages = []

	for migrator, filename in zip(migrators, configFiles):
		m = migrator(filename)
		msg = m.migrate()
		messages.append(msg)
	return list(itertools.chain(*messages))

if __name__ == '__main__':
	migrate_all()
