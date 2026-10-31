package local.medtermquest.app;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

@CapacitorPlugin(name="LearningData")
public final class LearningDataPlugin extends Plugin {
    private LearningDatabase database;
    @Override public void load() { database=new LearningDatabase(getContext()); }
    @PluginMethod public void load(PluginCall call) {
        try { LearningDatabase.Snapshot value=database.loadState();JSObject result=new JSObject();result.put("payload",value.payload==null?org.json.JSONObject.NULL:value.payload);result.put("revision",value.revision);call.resolve(result); }
        catch(Exception e){call.reject("無法開啟本機資料，原資料未清除："+e.getMessage());}
    }
    @PluginMethod public void commit(PluginCall call) {
        try {Object value=call.getData().opt("expectedRevision");if(!(value instanceof Number))throw new IllegalArgumentException("Missing revision");double number=((Number)value).doubleValue();if(!Double.isFinite(number)||number!=Math.floor(number)||number<0||number>9007199254740991L)throw new IllegalArgumentException("Invalid revision");long next=database.commitState(call.getString("payload"),((Number)value).longValue());JSObject result=new JSObject();result.put("revision",next);call.resolve(result);}
        catch(Exception e){call.reject("本機交易未完成，原資料保留："+e.getMessage());}
    }
    @Override protected void handleOnDestroy(){if(database!=null)database.close();}
}
