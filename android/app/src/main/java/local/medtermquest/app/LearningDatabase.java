package local.medtermquest.app;

import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteOpenHelper;
import org.json.JSONObject;
import java.nio.charset.StandardCharsets;

/** App-private SQLite document store; the portable TS core owns domain schemas. */
public final class LearningDatabase extends SQLiteOpenHelper {
    public static final int MAX_BYTES = 64 * 1024 * 1024;
    public static final class Snapshot {
        public final String payload; public final long revision;
        Snapshot(String payload, long revision) { this.payload=payload; this.revision=revision; }
    }
    public LearningDatabase(Context context) { super(context,"medterm-learning.db",null,1); setWriteAheadLoggingEnabled(true); }
    @Override public void onCreate(SQLiteDatabase db) {
        db.execSQL("CREATE TABLE learning_state (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL, payload TEXT NOT NULL)");
    }
    @Override public void onUpgrade(SQLiteDatabase db,int oldVersion,int newVersion) {
        throw new IllegalStateException("Unsupported database migration; existing data retained");
    }
    private Snapshot read(SQLiteDatabase db) {
        try(Cursor c=db.rawQuery("SELECT payload,revision FROM learning_state WHERE id=1",null)) {
            return c.moveToFirst()?new Snapshot(c.getString(0),c.getLong(1)):new Snapshot(null,0);
        }
    }
    public synchronized Snapshot loadState() { return read(getReadableDatabase()); }
    public synchronized long commitState(String payload,long expectedRevision) throws Exception {
        if(payload==null||payload.getBytes(StandardCharsets.UTF_8).length>MAX_BYTES) throw new IllegalArgumentException("Local state is too large");
        JSONObject root=new JSONObject(payload);
        if(root.getInt("schema")!=1||root.getString("installation").isEmpty()) throw new IllegalArgumentException("Unsupported state schema");
        root.getJSONArray("questions");root.getJSONArray("concepts");root.getJSONArray("events");root.getJSONObject("settings");root.getJSONArray("sessions");root.getJSONArray("reports");
        SQLiteDatabase db=getWritableDatabase();db.beginTransaction();
        try {
            Snapshot prior=read(db);
            if(prior.revision!=expectedRevision) throw new IllegalStateException("本機資料已更新，請重新開啟練習後再試。");
            if(expectedRevision<0||expectedRevision>=9007199254740991L) throw new IllegalArgumentException("Invalid revision");
            ContentValues values=new ContentValues();values.put("id",1);values.put("revision",expectedRevision+1);values.put("payload",payload);
            if(db.insertWithOnConflict("learning_state",null,values,SQLiteDatabase.CONFLICT_REPLACE)<0)throw new IllegalStateException("SQLite write failed");
            db.setTransactionSuccessful();return expectedRevision+1;
        } finally { db.endTransaction(); }
    }
}
