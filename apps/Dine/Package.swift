// swift-tools-version: 6.0

import PackageDescription

// Static libs cross-compiled by `tools/dine ios build-native` land here.
let nativeLibDir = Context.packageDirectory + "/../../out/ios/lib"

// The link driver gets --sysroot, not -isysroot, so clang never reads SDKSettings.json and stamps
// LC_BUILD_VERSION with sdk = minos. iOS then runs the app in compatibility mode (no Liquid
// Glass). Override it; lld keeps the last -platform_version. Keep iosSDK in sync with the Xcode
// SDK and iosMin with env.sh's DINE_IOS_MIN.
let iosMin = "17.4"
let iosSDK = "27.0"

let package = Package(
    name: "Dine",
    platforms: [
        .iOS(iosMin),
        .macOS(.v14),
    ],
    products: [
        // An xtool project should contain exactly one library product,
        // representing the main app.
        .library(
            name: "Dine",
            targets: ["Dine"]
        ),
    ],
    targets: [
        .systemLibrary(name: "CDineHello"),
        .systemLibrary(name: "CArtBridge"),
        .systemLibrary(name: "CDbgAgent"),
        .target(
            name: "Dine",
            dependencies: ["CDineHello", "CArtBridge", "CDbgAgent"],
            linkerSettings: [.unsafeFlags([
                "-L", nativeLibDir,
                "-Xlinker", "-platform_version", "-Xlinker", "ios",
                "-Xlinker", iosMin, "-Xlinker", iosSDK,
                "-Xlinker", "-force_load", "-Xlinker", nativeLibDir + "/libjavacore.a",
                "-Xlinker", "-force_load", "-Xlinker", nativeLibDir + "/libopenjdk.a",
                "-Xlinker", "-force_load", "-Xlinker", nativeLibDir + "/libwolfssljni.a",
                "-Xlinker", "-force_load", "-Xlinker", nativeLibDir + "/libruntimetests.a",
                "-Xlinker", "-force_load", "-Xlinker", nativeLibDir + "/libtranslation_layer_main.a",
            ])]
        ),
    ]
)
