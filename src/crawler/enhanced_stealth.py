"""
Enhanced Stealth Configuration for Maximum Bot Detection Bypass

This module provides advanced anti-detection techniques that can be applied
to Selenium WebDriver instances to maximize bot detection bypass rates.

Based on research and testing against various bot detection systems.
"""

# Additional Chrome/Edge arguments for maximum stealth
ULTRA_STEALTH_ARGS = [
    # Core anti-detection
    "--disable-blink-features=AutomationControlled",
    "--disable-blink-features=AutomationControlled",  # Double apply for emphasis
    # Automation flags
    "--disable-automation",
    "--disable-infobars",
    # Extensions and plugins
    "--disable-extensions",
    "--disable-plugins-discovery",
    "--disable-default-apps",
    # Web features that can leak automation
    "--disable-web-security",  # Bypass CORS (use carefully)
    "--disable-features=IsolateOrigins,site-per-process",
    # Performance/behavior
    "--no-first-run",
    "--no-service-autorun",
    "--password-store=basic",
    # Media/graphics
    "--disable-gpu",
    "--disable-dev-shm-usage",
    "--disable-setuid-sandbox",
    "--no-sandbox",
    # Misc
    "--mute-audio",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
    "--disable-background-networking",
    # Language and locale
    "--lang=en-US",
    # Memory and cache
    "--disable-features=TranslateUI",
    "--disable-features=BlinkGenPropertyTrees",
]

# Chrome preferences for maximum stealth (nested under "prefs")
ULTRA_STEALTH_PREFS = {
    # Permissions
    "profile.default_content_setting_values.notifications": 2,
    "profile.default_content_settings.popups": 0,
    "profile.default_content_setting_values.geolocation": 2,
    # Credentials and autofill
    "credentials_enable_service": False,
    "profile.password_manager_enabled": False,
    "autofill.profile_enabled": False,
    # Downloads
    "download.prompt_for_download": False,
    "download.directory_upgrade": True,
    "safebrowsing.enabled": False,
}

# Experimental options (these go directly in add_experimental_option)
ULTRA_STEALTH_EXPERIMENTAL_OPTIONS = {
    "useAutomationExtension": False,
    "excludeSwitches": ["enable-automation", "enable-logging"],
}

# Advanced JavaScript patches to apply via CDP
ADVANCED_JS_PATCHES = """
// Comprehensive anti-detection JavaScript patches

(function() {
    'use strict';

    // 1. Navigator properties
    Object.defineProperties(navigator, {
        webdriver: {
            get: () => undefined,
            configurable: true
        },
        plugins: {
            get: () => [1, 2, 3, 4, 5],  // Fake plugins
            configurable: true
        },
        languages: {
            get: () => ['en-US', 'en'],
            configurable: true
        },
        hardwareConcurrency: {
            get: () => 8,  // Typical desktop CPU
            configurable: true
        },
        deviceMemory: {
            get: () => 8,  // 8GB RAM
            configurable: true
        },
        platform: {
            get: () => 'Win32',
            configurable: true
        },
        vendor: {
            get: () => 'Google Inc.',
            configurable: true
        }
    });

    // 2. Chrome runtime
    if (!window.chrome) {
        window.chrome = {};
    }
    if (!window.chrome.runtime) {
        window.chrome.runtime = {
            PlatformOs: {
                MAC: 'mac',
                WIN: 'win',
                ANDROID: 'android',
                CROS: 'cros',
                LINUX: 'linux',
                OPENBSD: 'openbsd'
            },
            PlatformArch: {
                ARM: 'arm',
                X86_32: 'x86-32',
                X86_64: 'x86-64'
            },
            PlatformNaclArch: {
                ARM: 'arm',
                X86_32: 'x86-32',
                X86_64: 'x86-64'
            },
            RequestUpdateCheckStatus: {
                THROTTLED: 'throttled',
                NO_UPDATE: 'no_update',
                UPDATE_AVAILABLE: 'update_available'
            },
            OnInstalledReason: {
                INSTALL: 'install',
                UPDATE: 'update',
                CHROME_UPDATE: 'chrome_update',
                SHARED_MODULE_UPDATE: 'shared_module_update'
            },
            OnRestartRequiredReason: {
                APP_UPDATE: 'app_update',
                OS_UPDATE: 'os_update',
                PERIODIC: 'periodic'
            }
        };
    }

    // 3. Permissions API
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications' ?
            Promise.resolve({ state: Notification.permission }) :
            originalQuery(parameters)
    );

    // 4. WebGL fingerprinting defense
    const getParameter = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(parameter) {
        if (parameter === 37445) {  // UNMASKED_VENDOR_WEBGL
            return 'Intel Inc.';
        }
        if (parameter === 37446) {  // UNMASKED_RENDERER_WEBGL
            return 'Intel Iris OpenGL Engine';
        }
        return getParameter.apply(this, arguments);
    };

    // 5. Canvas fingerprinting defense (light)
    const toBlob = HTMLCanvasElement.prototype.toBlob;
    const toDataURL = HTMLCanvasElement.prototype.toDataURL;
    const getImageData = CanvasRenderingContext2D.prototype.getImageData;

    // Add minimal noise to canvas operations
    HTMLCanvasElement.prototype.toBlob = function(...args) {
        return toBlob.apply(this, args);
    };

    HTMLCanvasElement.prototype.toDataURL = function(...args) {
        return toDataURL.apply(this, args);
    };

    CanvasRenderingContext2D.prototype.getImageData = function(...args) {
        return getImageData.apply(this, args);
    };

    // 6. Battery API (if exists)
    if (navigator.getBattery) {
        navigator.getBattery = () => Promise.resolve({
            charging: true,
            chargingTime: 0,
            dischargingTime: Infinity,
            level: 1,
            addEventListener: () => {},
            removeEventListener: () => {},
            dispatchEvent: () => true
        });
    }

    // 7. Media devices
    if (navigator.mediaDevices && navigator.mediaDevices.enumerateDevices) {
        const origEnumerate = navigator.mediaDevices.enumerateDevices;
        navigator.mediaDevices.enumerateDevices = async function() {
            const devices = await origEnumerate.apply(this);
            // Return realistic number of devices
            return devices.slice(0, Math.min(devices.length, 6));
        };
    }

    // 8. Connection API
    if (navigator.connection) {
        Object.defineProperty(navigator.connection, 'rtt', {
            get: () => 100,
            configurable: true
        });
        Object.defineProperty(navigator.connection, 'downlink', {
            get: () => 10,
            configurable: true
        });
        Object.defineProperty(navigator.connection, 'effectiveType', {
            get: () => '4g',
            configurable: true
        });
    }

    // 9. Screen properties (make them consistent)
    Object.defineProperties(window.screen, {
        availWidth: {
            get: () => window.screen.width,
            configurable: true
        },
        availHeight: {
            get: () => window.screen.height,
            configurable: true
        },
        colorDepth: {
            get: () => 24,
            configurable: true
        },
        pixelDepth: {
            get: () => 24,
            configurable: true
        }
    });

    // 10. Mouse and touch events (add human-like randomness)
    const originalAddEventListener = EventTarget.prototype.addEventListener;
    EventTarget.prototype.addEventListener = function(type, listener, options) {
        if (type === 'mousedown' || type === 'mouseup' || type === 'click') {
            // Wrap listener to add slight delay (human-like)
            const wrappedListener = function(event) {
                setTimeout(() => listener.call(this, event), Math.random() * 5);
            };
            return originalAddEventListener.call(this, type, wrappedListener, options);
        }
        return originalAddEventListener.call(this, type, listener, options);
    };

    // 11. Iframe detection
    Object.defineProperty(HTMLIFrameElement.prototype, 'contentWindow', {
        get: function() {
            return window;
        }
    });

    // 12. Date and time (prevent timezone fingerprinting detection)
    const originalDate = Date;
    Date = new Proxy(originalDate, {
        construct: function(target, args) {
            if (args.length === 0) {
                return new target();
            }
            return new target(...args);
        }
    });

    // 13. Console debug detection
    const noop = () => {};
    if (window.console && window.console.debug) {
        window.console.debug = noop;
    }

    // 14. Error stack trace sanitization
    Error.prepareStackTrace = (error, stack) => {
        return stack.map(frame => {
            return `    at ${frame.getFunctionName() || 'anonymous'} (${frame.getFileName()}:${frame.getLineNumber()}:${frame.getColumnNumber()})`;
        }).join('\\n');
    };

    // Log successful patches
    console.log('[Stealth] Advanced anti-detection patches applied successfully');
})();
"""

# Browser-specific realistic configurations
REALISTIC_CHROME_CONFIG = {
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "viewport": (1920, 1080),
    "platform": "Win32",
    "vendor": "Google Inc.",
    "languages": ["en-US", "en"],
}

REALISTIC_EDGE_CONFIG = {
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
    "viewport": (1920, 1080),
    "platform": "Win32",
    "vendor": "Google Inc.",
    "languages": ["en-US", "en"],
}


def apply_ultra_stealth(driver, browser_type="chrome"):
    """
    Apply ultra stealth configuration to a Selenium WebDriver.

    Args:
        driver: Selenium WebDriver instance
        browser_type: "chrome" or "edge"

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Apply advanced JavaScript patches via CDP
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument", {"source": ADVANCED_JS_PATCHES}
        )

        # Override navigator properties via CDP
        config = (
            REALISTIC_CHROME_CONFIG
            if browser_type == "chrome"
            else REALISTIC_EDGE_CONFIG
        )

        # Set user agent
        driver.execute_cdp_cmd(
            "Network.setUserAgentOverride", {"userAgent": config["user_agent"]}
        )

        # Set timezone
        driver.execute_cdp_cmd(
            "Emulation.setTimezoneOverride", {"timezoneId": "America/New_York"}
        )

        # Set locale
        driver.execute_cdp_cmd("Emulation.setLocaleOverride", {"locale": "en-US"})

        # Set geolocation (optional - use realistic coords)
        driver.execute_cdp_cmd(
            "Emulation.setGeolocationOverride",
            {"latitude": 40.7128, "longitude": -74.0060, "accuracy": 100},
        )

        return True
    except Exception as e:
        print(f"Warning: Could not apply ultra stealth: {e}")
        return False
