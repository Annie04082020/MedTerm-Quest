package local.medtermquest.app;

import android.content.Context;
import android.content.pm.PackageManager;
import android.webkit.WebView;
import androidx.test.core.app.ActivityScenario;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import androidx.test.uiautomator.By;
import androidx.test.uiautomator.UiDevice;
import androidx.test.uiautomator.Until;
import org.json.*;
import org.junit.Test;
import org.junit.runner.RunWith;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import static org.junit.Assert.*;

/** Runs the actual APK WebView, native bridge and SQLite on the CI emulator. */
@RunWith(AndroidJUnit4.class)
public class OfflineLearningTest {
 private final Context context=InstrumentationRegistry.getInstrumentation().getTargetContext();
 private final AtomicReference<WebView> web=new AtomicReference<>();
 private void attach(ActivityScenario<MainActivity> scenario){scenario.onActivity(a->web.set(a.getBridge().getWebView()));}
 private Object evaluate(String expression)throws Exception{
  CountDownLatch latch=new CountDownLatch(1);AtomicReference<String> value=new AtomicReference<>();
  InstrumentationRegistry.getInstrumentation().runOnMainSync(()->web.get().evaluateJavascript(expression,r->{value.set(r);latch.countDown();}));
  assertTrue("WebView JS callback timed out",latch.await(15,TimeUnit.SECONDS));return new JSONTokener(value.get()).nextValue();
 }
 private void waitJs(String expression)throws Exception{long deadline=System.currentTimeMillis()+30000;while(System.currentTimeMillis()<deadline){if(Boolean.TRUE.equals(evaluate(expression)))return;Thread.sleep(100);}fail("Timed out: "+expression+" DOM="+evaluate("document.body.innerText.slice(0,2500)"));}
 private void click(String text)throws Exception{String value=JSONObject.quote(text);waitJs("Array.from(document.querySelectorAll('button')).some(e=>e.textContent.trim()==="+value+"&&!e.disabled)");evaluate("Array.from(document.querySelectorAll('button')).find(e=>e.textContent.trim()==="+value+").click();true");}
 private String asset(String name)throws Exception{try(java.io.InputStream s=InstrumentationRegistry.getInstrumentation().getContext().getAssets().open(name)){return new String(s.readAllBytes(),StandardCharsets.UTF_8);}}
 private void setText(String selector,String value)throws Exception{evaluate("(()=>{const e=document.querySelector("+JSONObject.quote(selector)+");Object.getOwnPropertyDescriptor(e.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype,'value').set.call(e,"+JSONObject.quote(value)+");e.dispatchEvent(new Event('input',{bubbles:true}));return true;})()");}
 @Test public void allSixGamesWorkOfflineAndSurviveActivityRestart()throws Exception{
  context.deleteDatabase("medterm-learning.db");String fixture=asset("test-state.json");JSONObject original=new JSONObject(fixture);JSONArray qs=original.getJSONArray("questions");Map<String,JSONObject> questions=new HashMap<>();for(int i=0;i<qs.length();i++)questions.put(qs.getJSONObject(i).getString("id"),qs.getJSONObject(i));
  try(LearningDatabase db=new LearningDatabase(context)){db.commitState(fixture,0);}
  String[] permissions=context.getPackageManager().getPackageInfo(context.getPackageName(),PackageManager.GET_PERMISSIONS).requestedPermissions;
  assertFalse("APK unexpectedly requests internet",permissions!=null&&Arrays.asList(permissions).contains("android.permission.INTERNET"));
  Set<String> modes=new HashSet<>();
  try(ActivityScenario<MainActivity> scenario=ActivityScenario.launch(MainActivity.class)){
   attach(scenario);waitJs("document.body.innerText.includes('每週學習與每日挑戰')");click("開始今日挑戰");
   for(int i=0;i<16;i++){
    waitJs("!!document.querySelector('.question-card')");String id=String.valueOf(evaluate("document.querySelector('.question-card').getAttribute('data-question-id')"));JSONObject q=questions.get(id);assertNotNull(id,q);String kind=q.getString("kind");modes.add(kind);
    switch(kind){
     case "multiple_choice":evaluate("Array.from(document.querySelectorAll('.choices input')).find(e=>e.value==="+JSONObject.quote(q.getString("answer"))+").click();true");break;
     case "matching":JSONObject pairs=q.getJSONObject("answer");for(Iterator<String> it=pairs.keys();it.hasNext();){String key=it.next();evaluate("(()=>{const e=document.getElementById("+JSONObject.quote("pair-"+key)+");e.value="+JSONObject.quote(pairs.getString(key))+";e.dispatchEvent(new Event('change',{bubbles:true}));return true;})()");}break;
     case "crossword":JSONObject words=q.getJSONObject("answer");JSONArray entries=q.getJSONArray("entries");for(int j=0;j<entries.length();j++){JSONObject e=entries.getJSONObject(j);setText("[aria-label='Clue "+e.getString("id")+" "+e.getString("direction")+"']",words.getString(e.getString("id")));}break;
     case "true_false":String answer=q.getString("answer"),truth=answer.equals("True")?"True":"False";evaluate("Array.from(document.querySelectorAll('.truth-options label')).find(e=>e.textContent.trim().startsWith("+JSONObject.quote(truth)+")).querySelector('input').click();true");if(!truth.equals("True"))setText("input.text-answer",answer.replaceFirst("^False:\\s*",""));break;
     default:setText("textarea.text-answer",q.getString("answer"));
    }
    click("Check answer");waitJs("!!document.querySelector('.answer-result.correct')");click("下一題");
    waitJs("!document.querySelector('.question-card')||document.querySelector('.question-card').getAttribute('data-question-id')!=="+JSONObject.quote(id));
   }
   assertEquals(6,modes.size());waitJs("document.body.innerText.includes('complete')");
   scenario.recreate();attach(scenario);waitJs("document.body.innerText.includes('16 / 16')&&document.body.innerText.includes('complete')");
   UiDevice.getInstance(InstrumentationRegistry.getInstrumentation()).takeScreenshot(new java.io.File(context.getExternalCacheDir(),"offline-games.png"));
  }
  try(LearningDatabase reopened=new LearningDatabase(context)){JSONObject saved=new JSONObject(reopened.loadState().payload);assertEquals(16,saved.getJSONArray("events").length());assertEquals(16,saved.getJSONArray("questions").length());}
 }
 @Test public void systemDocumentImportCancellationAndExportUseLocalFiles()throws Exception{
  context.deleteDatabase("medterm-learning.db");UiDevice device=UiDevice.getInstance(InstrumentationRegistry.getInstrumentation());
  try(ActivityScenario<MainActivity> scenario=ActivityScenario.launch(MainActivity.class)){
   attach(scenario);waitJs("document.body.innerText.includes('先匯入課程題庫')");click("題庫交換");click("選擇本機題庫或進度檔案");
   if(device.wait(Until.hasObject(By.desc("Show roots")),3000)){device.findObject(By.desc("Show roots")).click();device.wait(Until.hasObject(By.text("Downloads")),5000);device.findObject(By.text("Downloads")).click();}
   assertTrue("CI fixture not visible in Downloads",device.wait(Until.hasObject(By.text("medterm-ci-bank.json")),10000));device.findObject(By.text("medterm-ci-bank.json")).click();
   click("套用已驗證的匯入檔");waitJs("document.body.innerText.includes('匯入完成')");
   try(LearningDatabase db=new LearningDatabase(context)){assertEquals(16,new JSONObject(db.loadState().payload).getJSONArray("questions").length());}
   click("選擇本機題庫或進度檔案");Thread.sleep(1000);device.pressBack();waitJs("document.body.innerText.includes('已取消匯入')");
   click("匯出題庫");assertTrue(device.wait(Until.hasObject(By.text(java.util.regex.Pattern.compile("(?i)save"))),10000));device.findObject(By.text(java.util.regex.Pattern.compile("(?i)save"))).click();waitJs("document.body.innerText.includes('已將檔案儲存')");
   try(LearningDatabase db=new LearningDatabase(context)){assertEquals(0,new JSONObject(db.loadState().payload).getJSONArray("events").length());}
   device.takeScreenshot(new java.io.File(context.getExternalCacheDir(),"local-file-transfer.png"));
  }
 }
}
