package local.medtermquest.app;
import android.content.Context;
import androidx.test.core.app.ApplicationProvider;
import org.junit.*;
import org.junit.runner.RunWith;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.annotation.Config;
import static org.junit.Assert.*;

@RunWith(RobolectricTestRunner.class) @Config(sdk=28,manifest=Config.NONE)
public class LearningDatabaseTest {
 private LearningDatabase store;
 private static final String STATE="{\"schema\":1,\"installation\":\"test\",\"questions\":[],\"concepts\":[],\"events\":[],\"settings\":{},\"sessions\":[],\"reports\":[]}";
 @Before public void setup(){Context c=ApplicationProvider.getApplicationContext();c.deleteDatabase("medterm-learning.db");store=new LearningDatabase(c);}
 @After public void close(){store.close();}
 @Test public void survivesCloseAndReopen()throws Exception{assertEquals(0,store.loadState().revision);store.commitState(STATE,0);store.close();store=new LearningDatabase(ApplicationProvider.getApplicationContext());assertEquals(STATE,store.loadState().payload);assertEquals(1,store.loadState().revision);}
 @Test public void staleWritesDoNotOverwriteExistingState()throws Exception{store.commitState(STATE,0);try{store.commitState(STATE.replace("test","stale"),0);fail("stale write accepted");}catch(IllegalStateException expected){}assertEquals(STATE,store.loadState().payload);assertEquals(1,store.loadState().revision);}
 @Test public void invalidSchemasNeverResetTheDatabase()throws Exception{store.commitState(STATE,0);try{store.commitState(STATE.replace("\"schema\":1","\"schema\":9"),1);fail("schema accepted");}catch(IllegalArgumentException expected){}assertEquals(STATE,store.loadState().payload);}
}
