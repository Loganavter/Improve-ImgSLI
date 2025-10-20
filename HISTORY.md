# Development History

This document tracks the evolution of Improve-ImgSLI across releases and major refactors. It is migrated from the former "Development Story" section of README to keep the main page concise.

## September 2024 — First prototype
The journey of Improve ImgSLI began in September 2024, initially conceived with ChatGPT's assistance to address a personal need for straightforward image comparison in my work. The early version provided basic side-by-side functionality.

## October 2024 — Magnifier and drag-and-drop
The following month, October, marked an enhancement phase using Claude, which introduced a magnifier tool and drag-and-drop support, significantly improving usability.

## November 2024 — Magnifier refinements
By November, further refinements to the magnifier were implemented with Claude, including view freezing and merging capabilities. However, the codebase's expansion, coupled with Claude's 8k token context limit, made complete code regeneration impractical, necessitating manual integration of new features. Gemini was then employed to help manage these integrations, though not all AI-generated code was directly usable, leading to some features being postponed or temporarily disabled to maintain stability.

## December 2024 — Experiments and lessons
A brief period in early December saw an experiment with adaptive magnifier positioning tied to window resizing, which was ultimately set aside due to unsatisfactory results.

## January 2025 — Dynamic resizing
A turning point came in January 2025 when a user request for dynamic window resizing led to the exploration of DeepSeek. This AI, notable at the time for its Chain-of-Thought reasoning, successfully guided the implementation of this crucial feature, with Gemini then seamlessly incorporating it alongside other updates. See issue: https://github.com/Loganavter/Improve-ImgSLI/issues/1

## February 2025 — Feature growth and stability
February 2025 brought renewed focus on enhancing the application. Leveraging Claude Sonnet 3.7, features like dynamic image swapping, a multilingual dictionary, and further magnifier improvements were added, along with a helpful tooltip. Shortly thereafter, access to Grok 3—first via X, then its dedicated website—provided a significant boost. Grok 3's DeepThink model proved exceptionally effective at resolving persistent bugs, outperforming previous AIs, while its generous query limits and intelligent standard model streamlined development. Key contributions included optimized rendering, filename display and editing, and fixes for fullscreen mode.

## Late March 2025 — Cross-platform push
Late March 2025 was dedicated to cross-platform compatibility. Gemini and Grok, using their web search capabilities, assisted in drafting build and packaging scripts. While initial hopes for community maintenance of platform builds didn't materialize due to some skepticism about the project's AI-assisted origins, this solo effort, though time-intensive (taking considerable effort per platform), led to the discovery and resolution of several bugs, culminating in a successful cross-platform launch. Delays in Flathub publication until mid-April allowed for further bug fixes and the addition of a list cleanup feature.

## April 2025 — Persistence and settings
In April 2025, attention shifted back to addressing critical bugs, with continued reliance on Gemini. A major achievement during this period was the implementation of window state persistence—a feature that proved incredibly challenging but vastly improved user experience. A settings tab was also introduced, centralizing language selection, output image quality, and filename length preferences. Following these updates, Windows and Flatpak builds were refreshed. The current plan involves implementing one final feature and verifying the Flatpak maintenance pipeline before updating Windows and AUR builds, after which the project will likely enter a period of stability.

## May 2025 — Caching and architecture split
May 2025. I discovered Cursor AI, which allowed me to quickly implement three key features in this update using agents like ChatGPT 4.1, Sonnet 3.5, and Gemini 2.5 PRO, all within the free limit of 150 uses. These features included a smarter caching service that improved smoothness by approximately 2-3 times compared to the previous version, the ability to select magnifier interpolation, and quick image preview using the keyboard. Additionally, the project's structure became much more multi-layered and less coupled between modules. This refactoring required two days of collaboration with Gemini to break down two monolithic scripts into numerous services with separate folders. The entire process took about three days.

## June 2025 — UI style refactor
June 2025. With Gemini, I refactored the code once again. The application now features a qfluentwidgets style. It initially took a long time, but then I gave the project fork code with this GUI, and it went much faster, it took about 3 days. Caching was also further improved. The icons.py file was completely removed as it was no longer necessary.

## July 2025 — Rendering pipeline overhaul
July 2025. The solid architecture from the June refactoring allowed for another rapid development burst. This update took about 4-5 days, again with Gemini's assistance. The launcher.sh script was turned into a proper command-line utility for managing the environment. The rendering pipeline was overhauled to use a dynamic canvas, which allows the magnifier to draw outside the image bounds and also improves performance on large images and magnifiers due to more efficient data packaging. The magnifier also now correctly handles horizontal splitting. UI interaction was improved with long-press actions and scrollable selection dropdowns. Internally, all print statements were replaced with a standard logging system. The persistent bug with window geometry, however, remains. After over 20 failed attempts to fix it, it's clear the root cause is a race condition in how state signals are handled. This confirms the need to move away from the current semblance of an architecture to a full MVC/MVVM pattern, which will be the primary focus going forward.

## August 2025 — Full custom UI and MVP
August 2025. This update was born out of necessity. The qfluentwidgets library, while initially useful, became a major roadblock due to its extreme rigidity in customization. Discovering that simple layout logic was hardcoded in its C++ source was the final straw. This prompted a full rewrite of the user interface with 100% custom components. In parallel, the long-standing "god script" issue was tackled by migrating the entire application to a proper Model-View-Presenter (MVP) architecture. This new, solid foundation allowed for the rapid implementation of several new features: an image rating system, selectable light/dark themes, a display cache for performance with large files, and completely redesigned settings and help dialogs. The entire transformation was completed in about a week, exclusively with Gemini's help.

## Early October 2025 — Shared toolkit and UX polish
Early October 2025. With renewed access to Cursor AI, a significant unification of the codebase with another of my projects, Tkonverter, was carried out. The result is a shared library, shared_toolkit, which simplifies transferring functionality between projects. Following a user request, a feature for pasting images from the clipboard (Ctrl+V) was added. The user experience was substantially redesigned, introducing new customization options for the main comparison line and the magnifier's divider (controlling visibility, color, and thickness). System notifications on Linux were also fixed. In addition to Cursor, this update was developed with the active use of Gemini and Claude models, as well as new AI aggregator platforms, which helped accelerate the process. See issue: https://github.com/Loganavter/Improve-ImgSLI/issues/20
Further enhancements to the magnifier (precision controls and rendering tweaks), plus the addition of pixel/structural difference views and analysis tools (channels, edges, metrics). This batch of work took approximately 3–5 hours.
---

For earlier notes and context, see the original README history in the repository's commit log.
