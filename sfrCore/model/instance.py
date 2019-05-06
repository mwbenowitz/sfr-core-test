
import re
from datetime import datetime
from sqlalchemy import (
    Column,
    Date,
    ForeignKey,
    Integer,
    String,
    Unicode,
    PrimaryKeyConstraint
)
from sqlalchemy.orm import relationship, backref
from sqlalchemy.ext.associationproxy import association_proxy

from sfrCore.model.core import Base, Core
from sfrCore.model.measurement import INSTANCE_MEASUREMENTS, Measurement
from sfrCore.model.identifiers import INSTANCE_IDENTIFIERS, Identifier
from sfrCore.model.link import INSTANCE_LINKS, Link
from sfrCore.model.date import INSTANCE_DATES, DateField
from sfrCore.model.item import Item
from sfrCore.model.agent import Agent
from sfrCore.model.altTitle import INSTANCE_ALTS, AltTitle
from sfrCore.model.rights import Rights, INSTANCE_RIGHTS
from sfrCore.model.language import Language

from sfrCore.helpers.logger import createLog
from sfrCore.helpers.errors import DataError

logger = createLog('instances')


class Instance(Core, Base):
    """Instances describe specific versions (e.g. editions) of a work in the
    FRBR sfrCore.model. Each of these instance can have multiple items and be
    associated with various agents, measurements, links and identifiers."""
    __tablename__ = 'instances'
    id = Column(Integer, primary_key=True)
    title = Column(Unicode, index=True)
    sub_title = Column(Unicode)
    pub_place = Column(Unicode)
    edition = Column(Unicode)
    edition_statement = Column(Unicode)
    volume = Column(Unicode)
    table_of_contents = Column(Unicode)
    copyright_date = Column(Date)
    extent = Column(Unicode)
    
    work_id = Column(Integer, ForeignKey('works.id'))

    work = relationship(
        'Work',
        back_populates='instances'
    )
    items = relationship(
        'Item',
        back_populates='instance',
        collection_class=set
    )
    agents = association_proxy(
        'agent_instances',
        'agent'
    )
    measurements = relationship(
        'Measurement',
        secondary=INSTANCE_MEASUREMENTS,
        back_populates='instance',
        collection_class=set
    )
    identifiers = relationship(
        'Identifier',
        secondary=INSTANCE_IDENTIFIERS,
        back_populates='instance',
        collection_class=set
    )
    links = relationship(
        'Link',
        secondary=INSTANCE_LINKS,
        back_populates='instances',
        collection_class=set
    )
    alt_titles = relationship(
        'AltTitle',
        secondary=INSTANCE_ALTS,
        back_populates='instance',
        collection_class=set
    )

    RELS = [
        'formats',
        'agents',
        'identifiers',
        'measurements',
        'dates',
        'links',
        'alt_titles',
        'rights',
        'language'
    ]

    def __init__(self, title=None, edition=None, work=None, session=None):
        self.session = session
        self.title = title
        self.edition = edition
        self.work = work

    def __repr__(self):
        return '<Instance(title={}, edition={}, work={})>'.format(
            self.title,
            self.edition,
            self.work
        )
    
    def createTmpRelations(self, instanceData):
        for relType in Instance.RELS:
            tmpRel = '{}_tmp'.format(relType)
            setattr(self, tmpRel, instanceData.pop(relType, []))
            if getattr(self, tmpRel) is None: setattr(self, tmpRel, [])
    
    def removeTmpRelations(self):
        """Removes temporary attributes that were used to hold related objects.
        """
        for rel in Instance.RELS: delattr(self, '{}_tmp'.format(rel))

    @classmethod
    def updateOrInsert(cls, session, instanceData, work=None):
        """Check for existing instance, if found update that instance. If not
        found, create a new record."""

        # Check for a matching instance by identifiers (and volume if present)
        existingID = Instance.lookup(
            session,
            instanceData['identifiers'],
            instanceData.get('volume', None)
        )
        
        if existingID is not None:
            existing = session.query(Instance).get(existingID)

            if existing.work is None and work is not None: existing.work = work
            
            existing.update(session, instanceData)
            outInstance = existing
        else:
            outInstance = Instance.createNew(session, instanceData)
        
        return outInstance

    @classmethod
    def lookup(cls, session, identifiers, newVolume):
        """Query for an existing instance. Generally this will be returned
        by a simple identifier match, but if we have volume data, check to
        be sure that these are the same volume (generally only for) periodicals
        """
        existingID = Identifier.getByIdentifier(Instance, session, identifiers)

        if existingID is not None and newVolume is not None:
            logger.debug('Checking to see if volume records match')
            existingVol = session.query(Instance.volume)\
                .filter(Instance.id == existingID)\
                .one_or_none()
            if existingVol[0] != newVolume:
                logger.debug('Found matching volume {}'.format(existingVol[0]))
                existingID = None

        return existingID
    
    @classmethod
    def createNew(cls, session, instanceData):
        newInstance = cls(session=session)
        newInstance.createTmpRelations(instanceData)
        newInstance.insertData(instanceData)
        newInstance.removeTmpRelations()
        delattr(newInstance, 'session')
        return newInstance
    
    def insertData(self, instanceData):
        """Insert a new instance record"""
        logger.info('Inserting new instance record')
        for key, value in instanceData.items(): setattr(self, key, value)

        # Drop fields that should be targeted for works
        self.pop('series', None)
        self.pop('series_position', None)
        self.pop('subjects', [])
        
        self.addAgents()
        self.addIdentifiers()
        self.addAltTitles()
        self.addMeasurements()
        self.addLinks()
        self.addDates()
        self.addRights()
        self.insertLanguages(new=True)
        self.insertItems(new=True)

        logger.info('Inserted {}'.format(self))

    def update(self, session, instanceData):
        """Update an existing instance"""
        
        # Set fields targeted for works
        if self.work is not None:
            self.setWorkFields(
                instanceData.pop('series', None),
                instanceData.pop('series_position', None),
                instanceData.pop('subjects', [])
            )

        self.session = session
        self.createTmpRelations(instanceData)

        for field, value in instanceData.items():
            if(value is not None):
                setattr(self, field, value)

        self.updateAgents()
        self.updateIdentifiers()
        self.insertLanguages()
        self.insertItems()
        self.updateAltTitles()
        self.updateMeasurements()
        self.updateDates()
        self.updateLinks()
        self.updateRights()
        
        delattr(self, 'session')
        self.removeTmpRelations()
    
    def setWorkFields(self, series, position, subjects):
        if series: self.work.series = series
        if position: self.work.series_position = position
        if len(subjects): self.work.importSubjects(self.session, subjects)

    def addAgents(self):
        for agent in self.tmp_agents: self.addAgent(agent)
    
    def addAgent(self, agent):
        try:
            agentRec, roles = Agent.updateOrInsert(self.session, agent)
            for role in roles:
                AgentInstances(
                    agent=agentRec,
                    instance=self,
                    role=role
                )
        except DataError:
            logger.warning('Unable to read agent {}'.format(agent['name']))

    def updateAgents(self):
        for agent in self.tmp_agents: self.updateAgent(agent)
    
    def updateAgent(self, agent):
        try:
            agentRec, roles = Agent.updateOrInsert(self.session, agent)
            if roles is None: roles = ['author']
            for role in roles:
                if AgentInstances.roleExists(
                    self.session,
                    agentRec,
                    role,
                    self.id
                ) is None:
                    AgentInstances(agent=agentRec, instance=self, role=role)
        except DataError:
            logger.warning('Unable to read agent {}'.format(agent['name']))
    
    def addIdentifiers(self):
        self.identifiers = {
            Identifier.returnOrInsert(self.session, i) 
            for i in self.tmp_identifiers
        }

    def updateIdentifiers(self):
        for iden in self.tmp_identifiers: self.updateIdentifier(iden)
    
    def updateIdentifier(self, iden):
        try:
            self.identifiers.add(
                Identifier.returnOrInsert(self.session, iden)
            )
        except DataError as err:
            logger.warning('Received invalid identifier')
            logger.debug(err)
    
    def insertLanguages(self):
        languages = self.tmp_language
        if languages is not None:
            if isinstance(languages, str): languages = [languages]
            for lang in self.newData.tmp_language: self.updateLanguage(lang)
    
    def insertLanguage(self, lang):
        try:
            self.language.add(
                Language.updateOrInsert(self.session, lang)
            )
        except DataError:
            logger.warning('Unable to parse language {}'.format(lang))
    
    def insertItems(self):
        for item in self.tmp_formats:
            # Check if the provided record contains an epub that can be stored
            # locally. If it does, defer insert to epub creation process
            self.items.add(Item.updateOrInsert(self.session, item))
    
    def addAltTitles(self):
        self.alt_titles = { AltTitle(title=a) for a in self.tmp_alt_titles }

    def updateAltTitles(self):
        for altTitle in list(
            filter(
                lambda x: AltTitle.insertOrSkip(self.session, x, Instance, self.id),
                self.tmp_altTitles
            )
        ):
            self.alt_titles.add(AltTitle(title=altTitle))
    
    def addMeasurements(self):
        self.measurements = {
            Measurement.insert(m) for m in self.tmp_measurements
        }

    def updateMeasurements(self):
        for m in self.tmp_measurements:
            self.measurements.add(
                Measurement.updateOrInsert(self.session, m, Instance, self.id)
            )
    
    def addDates(self):
        self.dates = { DateField.insert(d) for d in self.tmp_dates }

    def updateDates(self):
        for d in self.tmp_dates:
            self.dates.add(
                DateField.updateOrInsert(self.session, d, Instance, self.id)
            )
    
    def addLinks(self):
        self.links = { Link(**l) for l in self.tmp_links }

    def updateLinks(self):
        for l in self.tmp_links:
            self.links.add(
                Link.updateOrInsert(self.session, l, Instance, self.id)
            )

    def addRights(self):
        self.rights = {
            Rights.insert(r, dates=r.pop('dates', []))
            for r in self.tmp_rights
        }

    def updateRights(self):
        for r in self.tmp_rights:
            self.rights.add(
                Rights.updateOrInsert(self.session, r, Instance, self.id)
            )
        

class AgentInstances(Core, Base):
    """Table relating agents and instances. Is instantiated as a class to
    allow the assigning of a 'role' to each relationship.
    (e.g. author, editor)"""

    __tablename__ = 'agent_instances'
    instance_id = Column(Integer, ForeignKey('instances.id'), primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey('agents.id'), primary_key=True, index=True)
    role = Column(String(64), primary_key=True)

    agentInstancesPkey = PrimaryKeyConstraint(
        'instance_id',
        'agent_id',
        'role',
        name='agent_instances_pkey'
    )

    instance = relationship(
        Instance,
        backref=backref('agent_instances', cascade='all, delete-orphan')
    )
    agent = relationship('Agent')

    @classmethod
    def roleExists(cls, session, agent, role, recordID):
        """Query database to see if relationship with role exists between
        agent and instance. Returns model instance if it does or None if it
        does not"""
        return session.query(cls)\
            .filter(cls.agent_id == agent.id)\
            .filter(cls.instance_id == recordID)\
            .filter(cls.role == role)\
            .one_or_none()
