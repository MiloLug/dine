# OS features: one stage each

M7 of `notes/atl-port.md`. An OS feature is an Android API whose implementation calls the host
OS: hardware such as sensors, the vibrator and location; system integration such as the
clipboard, share and notifications; and the OS's schedulers for background work (jobs, alarms).
Android's `Service` components, the code an app runs in the background, are not OS features:
item 21 maps foreground services to iOS, and starting apps as services is
`notes/service-management/proposal.md`.

ATL implements OS features with Linux desktop code (GTK, D-Bus portals, ALSA, libsecret, sysfs)
that only the gtk build has; headless and iOS builds throw `UnsatisfiedLinkError` when an app
reaches it. Each OS feature moves behind the `os` slot in a stage of its own. Item 1 builds the
OS features test APK and the slot; every later item adds its feature's section to that APK and
implements the feature. Slot rules and the milestone rule are in
`notes/atl-port.md`; what iOS runs while Dine is in the background is in
`notes/background-tasks.md`.

## Rules

- An item moves its feature's natives out of the gtk-only legacy list (`dine-atl/meson.build`)
  into shared JNI glue plus a `desktop-linux` backend, with no behaviour change on gtk, and adds
  `none` and `ios` backends.
- meson rejects `desktop-linux` without `ui=gtk` for an OS feature whose code needs GTK or the gtk
  host (GdkClipboard, GtkFileDialog, GtkMediaFile, the GApplication behind notifications); each
  item finds out whether its feature does. `util.h` pulls in no GTK.
- `none` answers what Android answers when the hardware or feature is absent, where Android has
  such an answer. It logs `os: none <feature> <call>` once per feature and call, so a triage
  still sees what an app asked for.
- `ios`: a call that must return at once (`hasVibrator`, `getActiveNetworkInfo`, `hasPrimaryClip`)
  reads a mirror the backend keeps current, or waits for UIKit's thread with `dispatch_sync`, as
  text measurement does. UIKit's thread never waits for the Android one;
  results reach the Android main thread through `loop_main_post`. Which thread each framework needs
  is checked in its item.
- Target: the item's section of the OS features APK, graded on headless against `none`'s answers
  and checked on the phone with `ios`: a `dbg smoke atl-os-features` step where the debug agent
  sees the result, by hand otherwise. gtk is checked by hand, since its answers depend on the
  machine (clipboard contents, `/dev/input`, portals). The gtk Gravity Defied smoke and the runtime
  suite keep passing.
- Order: reach-first. The OS features the triage APKs reach come first, then the ones common in
  apps, media, the two stubs, and last the ones that need parts of M8. M6c adds which APKs reach
  each item. Other notes name an item by its feature, not its number.
- A finished item gets an "as built" status in its section, as the milestones in
  `notes/atl-port.md` do.

Native paths below are under `dine-atl/src/api-impl-jni/`.

## 1. Base: the OS features test APK and the slot

- The APK: `dine-atl/tests/headless/os-features/`, built by `tests/harness/apk.py`. One activity
  runs each feature's section in order, logs `os-features: <feature> <step> <result>` and ends with
  `os-features done`.
- Runners: `run-os-features.sh` (graded on headless, run by hand on gtk), `linux smoke
  os-features`, the APK in `out/tests/apks` from `build-ios-atl.sh`, an AtlView tile,
  `dbg smoke atl-os-features`.
- The slot: the meson option from the slot table (one backend per feature: `desktop-linux`, `ios`
  or `none`), `src/slots/os.h`, `src/backends/os/{desktop-linux,none,ios}/`, and the
  `none` log line.
- Info.plist keys: `apps/Dine/xtool.yml`'s `infoPath` is accord's partial plist (icons, accent
  color), with no place for other keys. Usage strings (location, microphone), background modes
  and task identifiers (jobs, M8d) and document types (M8a) need keys merged into it.
- Done when: the APK logs `os-features done` on headless, gtk and the phone, with no feature
  sections yet.

## 2. Sensors

- Today: `sensors/android_hardware_SensorManager.c` polls sysfs IIO from a glib timeout. In Java,
  `getDefaultSensor` always returns a Sensor, the 4-argument `registerListener` returns true and
  never calls back, and the 3-argument one serves TYPE_ORIENTATION from
  `LocationManager.requestLocationUpdates` (the bearing).
- `none`: `getDefaultSensor` null and an empty sensor list, as on a device without sensors.
- `ios`: CoreMotion. Orientation comes from the device attitude, so sensors don't wait for the
  location item; whether `desktop-linux` keeps the bearing route is decided here.
- Reach: accelerometerdemo registers an accelerometer listener in `onCreate`; on headless it
  stops at `SensorManager.register_accelerometer_listener_native`.
- Done when: headless logs no sensors; the phone logs accelerometer readings.

## 3. Vibrator

- Today: on gtk `src/api-impl-jni/android_os_Vibrator.c` finds a vibra device through gudev
  (feedbackd's `FEEDBACKD_TYPE=vibra`) and plays evdev force feedback; the headless and iOS
  builds take a no-op stub, `src/shared/android_os_Vibrator.c` (Gravity Defied's keypad calls
  `View.performHapticFeedback`, which creates a Vibrator; a missing native threw out of its touch
  listener). `Vibrator.hasVibrator` is hardcoded true.
- Rework both completely if needed: the stub goes, and where `View.performHapticFeedback` goes
  (today `vibrate(10)`) is decided here; it draws nothing, so not the ui slot.
- `none`: `hasVibrator` false; `vibrate` does nothing.
- `ios`: haptics, Core Haptics for durations and patterns.
- Reach: multitouch references Vibrator and asks for the VIBRATE permission (static read).
- Done when: headless logs `hasVibrator` false; on the phone a 100 ms vibrate is felt (by hand).

## 4. Connectivity

- Today: `net/android_net_ConnectivityManager.c` answers from GNetworkMonitor: network available,
  metered, and `registerNetworkCallback`.
- `none`: a connected, unmetered network, so apps don't refuse to load.
- `ios`: NWPathMonitor, mirrored for the synchronous calls.
- Reach: Gravity Defied calls it only in `Helpers.isOnline`, whose callers are its level-download
  paths (`LevelsManager.downloadLevel`, `DownloadLevelsMenuScreen`, `WaitForNetworkConnection`);
  compose_demo's image loader references it (static reads).
- Done when: headless logs a connected network and a callback; on the phone the network state
  follows Wi-Fi going off and on (by hand).

## 5. Clipboard

- Today: `content/android_content_ClipboardManager.c` writes the GdkClipboard and reads nothing. In
  Java `getPrimaryClip` returns null, `hasPrimaryClip` false, and the change listeners do nothing.
  GdkClipboard reads are asynchronous while the Java calls are synchronous, so `desktop-linux`
  keeps a mirror of the system clipboard.
- `none`: an in-process clipboard: a copy pastes in Dine's apps and goes nowhere else.
- `ios`: UIPasteboard. `hasPrimaryClip` comes from `hasStrings`, which shows no prompt (iOS
  knowledge), and the contents are read only for a paste. Whether iOS 27 prompts when a sideloaded
  app reads another app's copy without a paste action is unverified.
- Copy and paste work as in a native app on iOS and gtk: select text, Copy from the system menu,
  paste in another app, and the other way round; an app's own Copy button reaches the same
  pasteboard. The selection and the edit menu belong to the ui slot (M4c).
- Done when: headless sets a clip, reads it back and gets the change listener; by hand on the
  phone and on gtk, text copied in an Android app pastes in another app, and back.

## 6. MIME lookup

- Today: `content/android_content_ContentResolver.c` (`native_query_file_info`) answers a file's
  MIME type and `_display_name` from GIO. `MimeTypeMap` is a plain Java table.
- `none`: the type from the extension through `MimeTypeMap`; the display name is the file's base
  name.
- `ios`: UTType from the extension; the base name.
- Done when: headless and the phone answer `image/png` for a .png, `text/plain` for a .txt, null
  for an unknown extension, and the display names.

## 7. Open links and files

- Today: `Activity.nativeOpenURI` opens a URI through libportal's OpenURI, `Context.nativeOpenFile`
  opens a file in another app, and `nativeStartExternalService` starts another ATL app's service
  over D-Bus (`content/android_content_Context.c`). The GVariant intent helpers in legacy
  `gtk_util.c` and the GVariant parcels move to `desktop-linux` here; notifications and the gtk
  host's actions use them too.
- `none`: `ActivityNotFoundException`, Android's answer when nothing handles an intent.
- `ios`: `UIApplication.open` for links, the open-in sheet (UIDocumentInteractionController) for
  files; another app's service stays `none` until multi-app MA7 (calls between apps through the
  `ipc` slot; on Linux its `unix` backend, with the D-Bus intent API kept as the desktop's entry,
  `notes/multi-app-support/design.md`).
- This item settles the Java table's "external intents sent over D-Bus" row in
  `notes/atl-port.md`.
- Done when: headless gets the exception for an https link; on the phone Safari opens it (by hand).

## 8. Share

- Today: ACTION_SEND goes to `nativeShareFile` (`content/android_content_Context.c`), a GTK dialog
  that offers the Email portal (`org.freedesktop.portal.Email`) and a Copy button.
- `none`: `ActivityNotFoundException`.
- `ios`: the share sheet (UIActivityViewController): Mail, Copy and other apps.
- Done when: headless gets the exception; on the phone the share sheet shows in `dbg ui ls` and
  closes.

## 9. File picker

- Today: `Activity.nativeFileChooser` (`app/android_app_Activity.c`) opens a GtkFileDialog, and
  `Activity` passes `GTK_FILE_CHOOSER_ACTION_*` ints (open, save, select folder).
  `content/android_atl_ATLMediaContentProvider.c` opens a GtkFileDialog to pick a media folder.
- ACTION_OPEN_DOCUMENT, ACTION_GET_CONTENT, ACTION_CREATE_DOCUMENT and ACTION_OPEN_DOCUMENT_TREE
  become neutral request kinds in place of the ints (the Java table's row in `notes/atl-port.md`).
- `none`: `RESULT_CANCELED`.
- `ios`: UIDocumentPickerViewController; the picked file reaches the app as a content URI.
- Done when: headless gets `RESULT_CANCELED`; on the phone the picker shows in `dbg ui ls`, and a
  file picked by hand is read.

## 10. Keystore

- Today: `security/android_security_keystore_AndroidKeyStore.c` keeps keys in libsecret; Context's
  static block registers the `AndroidKeyStore` provider.
- `none`: keys in memory for the life of the process. With several apps in one process the keys
  need to be per app (multi-app's app record).
- `ios`: the Keychain.
- Done when: headless generates an AES key and encrypts and decrypts with it; on the phone the key
  survives a relaunch.

## 11. Location

- Today: `location/android_location_LocationManager.c` uses libportal's location portal, off
  unless `ATL_UGLY_ENABLE_LOCATION` is set. `LocationManager` names its provider `"xdgportal"`;
  the name comes from the `os` slot instead (the Java table's row in `notes/atl-port.md`).
  Sensors' TYPE_ORIENTATION uses location today.
- `none`: no providers, `getLastKnownLocation` null, every provider disabled.
- `ios`: CoreLocation, with the iOS permission prompt and a usage string in Info.plist (base item).
- Done when: headless logs no providers; on the phone the prompt is accepted by hand and a fix
  arrives.

## 12. Audio output

- Today: `audio/android_media_AudioTrack.c` plays PCM through ALSA,
  `audio/android_media_SoundPool.c` plays short sounds through GtkMediaFile, and
  `audio/android_media_AudioManager.c` handles the volume through the ALSA mixer; `audio/audio.c`
  holds the ALSA helpers.
- `none`: AudioTrack consumes writes at the real-time rate, so a game's audio loop keeps its
  timing; SoundPool loads and plays silently; the volume is fixed.
- `ios`: AVAudioEngine for AudioTrack and SoundPool; AVAudioSession for volume and focus, its
  category picked from the app's audio usage (a game mixes with other audio, media takes over).
- Done when: on headless writing 1 s of a tone takes about 1 s; on the phone the tone is heard (by
  hand).

## 13. Media playback

- Today: `media/android_media_MediaPlayer.c` plays through GtkMediaFile.
- `none`: `prepare` fails and `onError` fires, as for an unsupported file.
- `ios`: AVPlayer (files, http streams, HLS).
- Done when: headless gets `onError`; on the phone a bundled clip is heard (by hand).

## 14. Microphone

- Today: `audio/android_media_AudioRecord.c` captures through ALSA, off unless
  `ATL_UGLY_ENABLE_MICROPHONE` is set.
- `none`: AudioRecord stays uninitialized, as on a device without a microphone.
- `ios`: AVAudioEngine's input, with the iOS permission prompt and a usage string in Info.plist
  (base item).
- Done when: headless logs an uninitialized recorder; on the phone, after the prompt, 1 s of
  recording has a level above silence (by hand).

## 15. Media codecs

- Today: `media/android_media_MediaCodec.c` decodes with FFmpeg (aac, mp3, opus, h264, vp8, vp9;
  VAAPI when present) and hands video frames over as GTK textures. `MediaCodec` calls
  `System.exit(1)` for a codec it doesn't know; the item makes it throw, as Android does.
- `none`: no codecs: `createDecoderByType` throws and the codec list is empty.
- `ios`: AudioToolbox for audio, VideoToolbox for video. Video into a Surface waits for SurfaceView
  (M9).
- Done when: headless gets the exception; on the phone an AAC frame decodes to PCM.

## 16. Wallpaper (stub)

- Today: `app/android_app_WallpaperManager.c` sets the wallpaper through libportal.
- `none`: `isSetWallpaperAllowed` false; `setBitmap` does nothing.
- `ios`: as `none`. iOS has no API for apps to set the wallpaper (iOS knowledge).
- Done when: headless and the phone log `none`'s answers.

## 17. Push (stub)

- Today: `content/android_content_Context.c` registers UnifiedPush over D-Bus (it exports a
  connector and registers with a distributor). Context's static block calls it for an app with a
  UnifiedPush receiver, so such an app throws before any UI on headless and iOS; `sendBroadcast`
  calls it too.
- `none`: registration never completes, as on Android without a distributor app.
- `ios`: as `none`. iOS has no UnifiedPush distributor, and APNs needs a paid developer account
  (iOS knowledge, `notes/background-tasks.md`).
- Done when: headless and the phone register and get no message.

## 18. Notifications

- Today: `app/android_app_NotificationManager.c` sends GApplication desktop notifications, with
  actions as GVariant intents. `Service.stopForeground(true)` cancels through it. Toast belongs to
  the ui slot (M6b3).
- `none`: `notify` does nothing; `areNotificationsEnabled` false.
- `ios`: UNUserNotificationCenter local notifications, after the iOS permission prompt. Whether a
  free account gets the permission is open (`notes/background-tasks.md`, question 5); M8d's
  answer may change this design.
- A tap delivers the notification's PendingIntent to the running app. A tap after Dine was killed
  has to start the app, which needs M8a. With several apps the PendingIntent is a registry row
  that reaches its owning app (multi-app MA1, MA7), and a tap after iOS ended Dine loads only that
  app (MA8).
- Done when: headless notifies and cancels; on the phone the notification shows and a tap opens the
  app (by hand).

## 19. Media session

- Today: `media/android_media_session_MediaSession.c` exports MPRIS over D-Bus;
  `NotificationManager.c` owns the bus name, and a MediaStyle notification calls `nativeShowMPRIS`.
- `none`: metadata and commands do nothing.
- `ios`: the Now Playing info and remote commands (lock screen, Control Center). Dine has one Now
  Playing; which of several apps holds it is open (multi-app MA8).
- Needs: playing on after Dine leaves the front waits for M8d's answer on background audio.
- Done when: headless sets metadata and state; on the phone the lock screen shows them (by hand).

## 20. Downloads

- Today: `DownloadManager.enqueue` logs and returns 0; nothing downloads.
- `desktop-linux` and `none`: DownloadManager in shared Java on a worker thread: enqueue, query,
  the files, `ACTION_DOWNLOAD_COMPLETE`.
- `ios`: a background URLSession takes the transfer, so it continues while Dine is suspended
  (iOS knowledge, `notes/background-tasks.md`).
  Delivering the completion after iOS relaunches Dine in the background needs a start path without
  UI, after M8a and M8d; M8d's answers may change this design.
- Done when: headless downloads a small file with `--network` and gets the completion broadcast;
  on the phone a download finishes while Dine is in the background (by hand).

## 21. Jobs and foreground services (JobScheduler, WorkManager, AlarmManager, Service)

- Today: `Service.startForeground` logs and keeps the id. AlarmManager and `JobScheduler.schedule`
  post to the app's main Looper with `postDelayed` (a job's service starts after its minimum
  latency),
  so alarms and jobs run only while Dine runs; `JobScheduler.enqueue` is a stub.
- `desktop-linux` and `none`: in-process, as today.
- `ios`: BGProcessingTask for jobs, BGContinuedProcessingTask for foreground services, and the
  opt-in keep-alive (`notes/background-tasks.md`, Options), chosen from M8d's answers; their
  Info.plist keys come through the base item.
- Needs: M8b (the iOS lifecycle) and M8d (the background probes).
- Reach: Gravity Defied sets an AlarmManager alarm in `GDActivity.doRestartApp` (static read).
- Done when: headless runs a job and an alarm (in-process, as today); on the phone a job runs
  after Dine went to the background (by hand; it may take hours).

## Later

- MIME lookup by a sniffer of its own: magic bytes and the extension, maybe more on iOS.
