import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from sfrCore.model.core import Base
from sfrCore.helpers.logHelpers import createLog

class SessionManager():
    def __init__(self, user=None, pswd=None, host=None, port=None, db=None):
        self.user = user if user else os.environ.get('DB_USER', None)
        self.pswd = pswd if pswd else os.environ.get('DB_PSWD', None)
        self.host = host if host else os.environ.get('DB_HOST', None)
        self.port = port if port else os.environ.get('DB_PORT', None)
        self.db = db if db else os.environ.get('DB_NAME', None)
        
        self.engine = None
        self.session = None
        
        self.logger = createLog('dbManager')
    
    def generateEngine(self):
        try:
            self.engine = create_engine(
                'postgresql://{}:{}@{}:{}/{}'.format(
                    self.user,
                    self.pswd,
                    self.host,
                    self.port,
                    self.db
                )
            )
        except Exception as e:
            self.logger.error(e)
            raise e

    def initializeDatabase(self):
        if not self.engine.dialect.has_table(self.engine, 'works'):
            Base.metadata.create_all(self.engine)

    def createSession(self, autoflush=True):
        if not self.engine: self.generateEngine()
        self.session = sessionmaker(bind=self.engine, autoflush=autoflush)()
        return self.session

    def startSession(self):
        self.session.begin_nested()

    def commitChanges(self):
        self.session.commit()

    def closeConnection(self):
        self.commitChanges()
        self.session.close()
        self.engine.dispose()
