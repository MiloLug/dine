# Background work, downloads and notifications

How Android apps expect to run when they are not on screen, what iOS offers instead, and what Dine
can map between the two. Why Dine has one process and what limits that brings is in
`notes/meta.md`; the service-backend plan (M7) is in `notes/service-impl.md`; tool commands are in
`CLAUDE.md`.

Marks used below:
- **Checked**: read in this repo.
- **iOS knowledge**: from general knowledge of iOS, not tested on the iPhone 13 (iOS 27.0.1) or
  against Apple's docs. Treat as a claim to test.

## Status in the repo (checked)

- `android.app.NotificationManager` (ATL) calls natives in
  `android_app_NotificationManager.c`, which sends GIO desktop notifications. That file is in the
  meson list of "natives not yet behind a slot, built only with ui=gtk", so the iOS build has no
  implementation. A `notify()` call on iOS has no native to reach (not run on the phone).
- `android.app.DownloadManager` (ATL) is a stub: `enqueue()` logs and returns 0, `query()` returns an
  empty cursor.
- `android.app.Service` (ATL) logs its lifecycle calls. Foreground-service behavior was not
  checked.
- Dine has no background code: no `UIBackgroundModes`, `beginBackgroundTask`, `URLSession` or
  `BGTaskScheduler` in `apps/Dine/Sources`.
- `notes/service-impl.md` plans notifications on `UNUserNotificationCenter` (its notifications
  item).
- With no keep-alive, iOS suspends Dine within seconds of leaving the foreground. The VM and every
  Android app in it stop (same process, `notes/meta.md`).

## Android model

- The process stays alive after the user leaves the app. It is cached and killed only for memory or
  policy (Doze, App Standby buckets, background execution limits).
- App code runs in the background through:
  - a foreground service: a long-running service with a persistent notification and a declared
    type (`dataSync`, `mediaPlayback`, `location`, and others); the process stays alive and runs
    arbitrary logic;
  - `WorkManager` / `JobScheduler`: code runs when constraints hold (network, charging), at a time
    the system picks, with retries;
  - `AlarmManager`, broadcast receivers and FCM push: code is woken at a time or on an event.
- `DownloadManager` is a system service for plain "fetch this URL" downloads. Apps with their own
  download logic (page fetching, parsing, chunking, batches) run it in a foreground service or a
  `WorkManager` job.

These points are iOS-knowledge-level for Android as well; none was verified against AOSP here.

## iOS model (iOS knowledge)

- The process is suspended seconds after backgrounding. No threads or timers run.
- The system runs work for the app only in these forms:
  - **Background `URLSession`** (`URLSessionConfiguration.background(withIdentifier:)`): the
    `nsurlsessiond` daemon performs a list of requests declared in advance. It continues while the
    app is suspended and survives the app being terminated by the system, not a force-quit by the
    user. On completion iOS relaunches the app for a few seconds to deliver events
    (`handleEventsForBackgroundURLSession`). No app logic runs between the requests; the app can
    enqueue the next requests during a wake-up.
  - **`beginBackgroundTask`**: about 30 s of extra run time after backgrounding. The length is
    unverified for iOS 27.
  - **`BGProcessingTask`**: the app's own code, including a VM, for minutes. The system picks the
    time, typically idle, charging and on a network. No guaranteed time; rarely opened apps get few
    runs. The system can end it early through the expiration handler. Needs the identifier in the
    `BGTaskSchedulerPermittedIdentifiers` Info.plist key.
  - **`BGAppRefreshTask`**: about 30 s, scheduled around when the user tends to open the app.
  - **`BGContinuedProcessingTask`** (iOS 26 and later, recalled from WWDC25): the user starts a job in
    the foreground and it continues after backgrounding, with a system progress UI. The closest
    iOS analog of an Android foreground service for a user-initiated job. Limits are unknown.
  - **`UIBackgroundModes`** (audio, location, VoIP, and others): keeps the process running for the
    declared purpose. Using it as a generic keep-alive violates App Store rules; on a sideload
    nothing reviews it.
- Local notifications (`UNUserNotificationCenter`) need no push entitlement and map from the
  `Notification` fields (title, text, actions, tap intent).
- Remote push needs APNs: the `aps-environment` entitlement and a paid developer account. A free
  Apple ID, as used for Dine, is expected not to have it.

## Mapping Android to iOS

| Android | iOS | Fit |
|---|---|---|
| `NotificationManager.notify` | `UNUserNotificationCenter` local notification | good; needs an iOS notifications service backend and a permission prompt |
| `PendingIntent` on a notification tap | notification response delegate, then the Activity | needs a route from the delegate to the VM |
| `DownloadManager` | background `URLSession` | good; the API is already "request it, the system does it". The completion broadcast (`ACTION_DOWNLOAD_COMPLETE`) fires on the relaunch wake-up |
| `WorkManager` / `JobScheduler` | `BGProcessingTask` | deferred, constrained, system-timed on both; iOS runs it later and less often |
| Foreground service, user-initiated job | `BGContinuedProcessingTask`, or a keep-alive mode | possible; untested |
| App's own downloader on threads (OkHttp, a manga downloader) | foreground only by default | stops about 30 s after backgrounding unless one of the rows above or a keep-alive applies |
| `AlarmManager` exact times | scheduled local notification at that time | the notification shows; app code does not run at that time |
| FCM push | none | needs APNs, a relay from FCM to APNs and Play Services stubs |

## Complex downloaders

An app that talks to a page or service, decides the next request from each response, batches or
chunks has app logic in the loop. The system cannot run that logic while the process is suspended.

Two ways it can still continue in the background:
- **Continued task or keep-alive.** A `BGContinuedProcessingTask` for a user-started download, or a
  keep-alive session (silent audio, location), keeps the VM running. Location is not affected by
  another app playing audio. Whether a silent-audio session survives another app taking the audio
  route (YouTube), possibly with the mix-with-others option, is unknown.
- **Split plan.** The small part that needs logic (fetch a chapter page, parse the image URLs)
  runs while Dine is running. The large part (the images) is handed to a background `URLSession`
  in one batch. This needs a bridge in Dine's HTTP layer, because the Android app does its own
  downloads and would not hand the list to the system by itself.

Target scenario: "start a manga download, switch to another app". Without any of the above, the
download freezes until Dine is in front again.

## Open questions (test on the phone)

1. Does a free-account sideloaded app get `BGTaskScheduler` runs on iOS 27, and how often?
2. Does `BGContinuedProcessingTask` exist and run in this setup, and with what time and resource
   limits? Does it keep the VM's threads running when the user switches to another app?
3. How long does `beginBackgroundTask` give on iOS 27?
4. Does a silent-audio keep-alive survive another app playing audio (non-mixing and mixing
   session options)? How long does it survive overall, and what does it cost in battery?
5. Is `UNUserNotificationCenter` authorization granted to a free-account sideloaded app?
6. Does `AlarmManager` map to scheduled local notifications for the apps that matter, or is
   firing app code at a set time required?
7. Does ATL's `Service` implement `startForeground`, and what should a foreground service request
   do in Dine (start a continued task, start a keep-alive, or nothing)?
8. A keep-alive keeps every Android app in the shared process alive, not only the one that asked.
   Is that acceptable, and is it per-app opt-in?

## Options

1. Foreground-only by default, plus an iOS `DownloadManager` on background `URLSession` and an iOS
   notifications service on `UNUserNotificationCenter`. Works regardless of the open questions
   above, except 5.
2. Add `BGProcessingTask` for `WorkManager` jobs and `BGContinuedProcessingTask` for foreground
   services once questions 1 and 2 are answered.
3. Add an opt-in keep-alive mode (audio or location) for apps with their own long downloaders, after
   questions 4 and 8. Fragile and costs battery.
4. Document conversational downloaders as "works only while Dine is open" until one of the above
   exists.

Order: M8d in `notes/atl-port.md` answers the open questions above on the phone first; the
notifications, media session, downloads and jobs items of `notes/service-impl.md` build on its
answers.
