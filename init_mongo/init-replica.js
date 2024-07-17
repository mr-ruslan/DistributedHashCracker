config = {
    _id: "rs0",
    members: [
      { _id: 0, host: "mongodb_0:27017" },
      { _id: 1, host: "mongodb_1:27017" },
      { _id: 2, host: "mongodb_2:27017" }
    ]
  }
  
rs.initiate(config);

rs.conf();

db = connect("mongodb://mongodb_0:27017,mongodb_1:27017,mongodb_2:27017/appdatabase?replicaSet=rs0");
  
db.crack.createIndex({"request_id": 1},{unique: true})