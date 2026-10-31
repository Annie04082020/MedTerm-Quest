package local.medtermquest.app;

import android.app.Activity;
import android.content.Intent;
import android.database.Cursor;
import android.net.Uri;
import android.provider.OpenableColumns;
import androidx.activity.result.ActivityResult;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.ActivityCallback;
import com.getcapacitor.annotation.CapacitorPlugin;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.nio.charset.CodingErrorAction;

/** SAF grants access only to the document explicitly selected by the user. */
@CapacitorPlugin(name="LocalDocuments")
public final class LocalDocumentsPlugin extends Plugin {
    private static final int MAX_BYTES=30*1024*1024;
    @PluginMethod public void openPackage(PluginCall call){
        Intent intent=new Intent(Intent.ACTION_OPEN_DOCUMENT);intent.addCategory(Intent.CATEGORY_OPENABLE);intent.setType("*/*");
        intent.putExtra(Intent.EXTRA_MIME_TYPES,new String[]{"application/json","text/plain","application/octet-stream"});intent.putExtra(Intent.EXTRA_LOCAL_ONLY,true);
        startActivityForResult(call,intent,"opened");
    }
    @PluginMethod public void savePackage(PluginCall call){
        String text=call.getString("text"),name=call.getString("name");
        if(text==null||text.getBytes(StandardCharsets.UTF_8).length>MAX_BYTES||name==null||!name.matches("medterm-[a-z]+-\\d{4}-\\d{2}-\\d{2}\\.json")){call.reject("匯出檔案無效或超過 30 MiB。");return;}
        Intent intent=new Intent(Intent.ACTION_CREATE_DOCUMENT);intent.addCategory(Intent.CATEGORY_OPENABLE);intent.setType("application/json");intent.putExtra(Intent.EXTRA_TITLE,name);intent.putExtra(Intent.EXTRA_LOCAL_ONLY,true);
        startActivityForResult(call,intent,"saved");
    }
    private Uri selected(PluginCall call,ActivityResult result){
        if(call==null)return null;
        if(result.getResultCode()!=Activity.RESULT_OK||result.getData()==null||result.getData().getData()==null){JSObject answer=new JSObject();answer.put("cancelled",true);call.resolve(answer);return null;}
        Uri uri=result.getData().getData();if(!"content".equals(uri.getScheme())){call.reject("請選擇裝置上的文件。");return null;}return uri;
    }
    @ActivityCallback private void opened(PluginCall call,ActivityResult result){
        Uri uri=selected(call,result);if(uri==null)return;
        execute(()->{try{
            String name="bank.json";try(Cursor c=getContext().getContentResolver().query(uri,null,null,null,null)){
                if(c!=null&&c.moveToFirst()){int size=c.getColumnIndex(OpenableColumns.SIZE),title=c.getColumnIndex(OpenableColumns.DISPLAY_NAME);if(size>=0&&!c.isNull(size)&&c.getLong(size)>MAX_BYTES)throw new IllegalArgumentException("檔案超過 30 MiB");if(title>=0)name=c.getString(title);}
            }
            ByteArrayOutputStream bytes=new ByteArrayOutputStream();try(InputStream stream=getContext().getContentResolver().openInputStream(uri)){
                if(stream==null)throw new IllegalArgumentException("文件無法開啟");byte[] buffer=new byte[8192];int n;while((n=stream.read(buffer))!=-1){if(bytes.size()+n>MAX_BYTES)throw new IllegalArgumentException("檔案超過 30 MiB");bytes.write(buffer,0,n);}
            }
            String text=StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(bytes.toByteArray())).toString();
            JSObject answer=new JSObject();answer.put("cancelled",false);answer.put("text",text);answer.put("name",name);call.resolve(answer);
        }catch(Exception e){call.reject("未匯入，原資料保留："+e.getMessage());}});
    }
    @ActivityCallback private void saved(PluginCall call,ActivityResult result){
        Uri uri=selected(call,result);if(uri==null)return;
        execute(()->{try(OutputStream stream=getContext().getContentResolver().openOutputStream(uri,"wt")){
            if(stream==null)throw new IllegalArgumentException("文件無法寫入");stream.write(call.getString("text").getBytes(StandardCharsets.UTF_8));stream.flush();JSObject answer=new JSObject();answer.put("cancelled",false);call.resolve(answer);
        }catch(Exception e){call.reject("匯出未完成，本機學習資料不變："+e.getMessage());}});
    }
}
