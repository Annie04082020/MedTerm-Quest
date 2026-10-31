package local.medtermquest.app;

import com.getcapacitor.BridgeActivity;
import android.os.Bundle;

public class MainActivity extends BridgeActivity {
    @Override public void onCreate(Bundle savedInstanceState){
        registerPlugin(LearningDataPlugin.class);registerPlugin(LocalDocumentsPlugin.class);super.onCreate(savedInstanceState);
    }
}
