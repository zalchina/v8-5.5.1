V8 JavaScript Engine
=============

V8 is Google's open source JavaScript engine.

V8 implements ECMAScript as specified in ECMA-262.

V8 is written in C++ and is used in Google Chrome, the open source
browser from Google.

V8 can run standalone, or can be embedded into any C++ application.

V8 Project page: https://github.com/v8/v8/wiki


Get The Dependencies
=============

Checkout [depot tools](http://www.chromium.org/developers/how-tos/install-depot-tools), 

After adding depot_tools to System `PATH`, then run

```
python download_deps.py
```

This will download all dependencies of V8 needed.

If you don't have CLANG installed on your PC, you should execute

```
python tools/clang/scripts/update.py --if-needed
```

On MacOS, you should make sure that `XCode Command Line Tools` is installed on your machine.

Build V8 With GN
============

A **Linux build machine** capable of building V8 for Linux. Other (Mac/Windows) platforms are not supported for Android.

First, generate the necessary build files:

```
gn args out.gn/android
```


```
gn gen out.gn/android --args='is_debug=false target_cpu="arm64" v8_target_cpu="arm64" target_os="android"'
```

```
ninja -C out.gn/android v8
```

Build V8 With GYP
============

```
make android_arm.release -j 16 android_ndk_root=... 
```


Contributing
=============

Please follow the instructions mentioned on the
[V8 wiki](https://github.com/v8/v8/wiki/Contributing).
