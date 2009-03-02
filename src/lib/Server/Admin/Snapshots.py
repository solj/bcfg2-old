import Bcfg2.Server.Admin
import sqlalchemy, sqlalchemy.orm
import Bcfg2.Server.Snapshots
import Bcfg2.Server.Snapshots.model

class Snapshots(Bcfg2.Server.Admin.Mode):
    __shorthelp__ = "Interact with the Snapshots system"
    __longhelp__ = (__shorthelp__)
    __usage__ = ("bcfg2-admin snapshots [init|query qtype] ")

    q_dispatch = {'client':Bcfg2.Server.Snapshots.model.Client,
                  'group':Bcfg2.Server.Snapshots.model.Group,
                  'snapshot':Bcfg2.Server.Snapshots.model.Snapshot,
                  }

    def __init__(self, configfile):
        Bcfg2.Server.Admin.Mode.__init__(self, configfile)
        self.session = Bcfg2.Server.Snapshots.setup_session(debug=True)

    def __call__(self, args):
        if args[0] == 'query':
            if args[1] in self.q_dispatch:
                q_obj = self.q_dispatch[args[1]]
                results = self.session.query(q_obj).all()
            else:
                print 'error'
                raise SystemExit, 1
            for result in results:
                print result.name
        elif args[0] == 'init':
            engine = create_engine(Bcfg2.Server.Snapshots.db_from_config(), echo=True)
            metadata = Base.metadata
            metadata.create_all(engine) 
            Session = sessionmaker()
            Session.configure(bind=engine)
            session = Session()
            session.commit()
