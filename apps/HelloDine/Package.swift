// swift-tools-version: 6.0

import PackageDescription

// Static libs cross-compiled by scripts/build-ios-native.sh land here.
let nativeLibDir = Context.packageDirectory + "/../../out/ios/lib"

let package = Package(
    name: "HelloDine",
    platforms: [
        .iOS(.v17),
        .macOS(.v14),
    ],
    products: [
        // An xtool project should contain exactly one library product,
        // representing the main app.
        .library(
            name: "HelloDine",
            targets: ["HelloDine"]
        ),
    ],
    targets: [
        .systemLibrary(name: "CDineHello"),
        .target(
            name: "HelloDine",
            dependencies: ["CDineHello"],
            linkerSettings: [.unsafeFlags(["-L", nativeLibDir])]
        ),
    ]
)
