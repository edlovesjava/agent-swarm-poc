/**
 * 8x8 LED Matrix Simulator
 * For prototyping ATtiny85 applications
 */

const Simulator = {
    // Matrix state: 8x8 grid, each cell can be 0 (off) or a color string
    matrix: [],

    // Button states
    buttons: {
        a: false,
        b: false
    },

    // Button event callbacks
    buttonCallbacks: {
        onAPress: null,
        onARelease: null,
        onBPress: null,
        onBRelease: null
    },

    // Timing
    frameCount: 0,
    lastFrameTime: 0,
    fps: 0,
    targetFPS: 30,
    paused: false,

    // Registered apps
    apps: {},
    currentApp: null,

    // DOM elements
    elements: {
        matrix: null,
        leds: [],
        btnA: null,
        btnB: null,
        appSelect: null,
        statusBar: null,
        fpsDisplay: null,
        frameDisplay: null,
        currentAppDisplay: null
    },

    /**
     * Initialize the simulator
     */
    init() {
        // Initialize matrix state (all off)
        this.clearMatrix();

        // Cache DOM elements
        this.elements.matrix = document.getElementById('matrix');
        this.elements.btnA = document.getElementById('btnA');
        this.elements.btnB = document.getElementById('btnB');
        this.elements.appSelect = document.getElementById('appSelect');
        this.elements.statusBar = document.getElementById('statusBar');
        this.elements.fpsDisplay = document.getElementById('fps');
        this.elements.frameDisplay = document.getElementById('frameCount');
        this.elements.currentAppDisplay = document.getElementById('currentApp');

        // Create LED elements
        this.createLEDs();

        // Set up input handlers
        this.setupInputHandlers();

        // Populate app selector
        this.updateAppSelector();

        // Start render loop
        this.lastFrameTime = performance.now();
        requestAnimationFrame(() => this.gameLoop());

        this.log('Simulator initialized');
    },

    /**
     * Create the 8x8 grid of LED elements
     */
    createLEDs() {
        this.elements.matrix.innerHTML = '';
        this.elements.leds = [];

        for (let y = 0; y < 8; y++) {
            for (let x = 0; x < 8; x++) {
                const led = document.createElement('div');
                led.className = 'led';
                led.dataset.x = x;
                led.dataset.y = y;
                this.elements.matrix.appendChild(led);
                this.elements.leds.push(led);
            }
        }
    },

    /**
     * Set up keyboard and mouse input handlers
     */
    setupInputHandlers() {
        // Keyboard events
        document.addEventListener('keydown', (e) => this.handleKeyDown(e));
        document.addEventListener('keyup', (e) => this.handleKeyUp(e));

        // Mouse events for buttons
        this.elements.btnA.addEventListener('mousedown', () => this.pressButton('a'));
        this.elements.btnA.addEventListener('mouseup', () => this.releaseButton('a'));
        this.elements.btnA.addEventListener('mouseleave', () => this.releaseButton('a'));

        this.elements.btnB.addEventListener('mousedown', () => this.pressButton('b'));
        this.elements.btnB.addEventListener('mouseup', () => this.releaseButton('b'));
        this.elements.btnB.addEventListener('mouseleave', () => this.releaseButton('b'));

        // Touch events for mobile
        this.elements.btnA.addEventListener('touchstart', (e) => {
            e.preventDefault();
            this.pressButton('a');
        });
        this.elements.btnA.addEventListener('touchend', () => this.releaseButton('a'));

        this.elements.btnB.addEventListener('touchstart', (e) => {
            e.preventDefault();
            this.pressButton('b');
        });
        this.elements.btnB.addEventListener('touchend', () => this.releaseButton('b'));

        // App selector
        this.elements.appSelect.addEventListener('change', (e) => {
            this.loadApp(e.target.value);
        });
    },

    /**
     * Handle key down events
     */
    handleKeyDown(e) {
        const key = e.key.toLowerCase();

        if (key === 'a' || key === 'z') {
            e.preventDefault();
            this.pressButton('a');
        } else if (key === 'b' || key === 'x') {
            e.preventDefault();
            this.pressButton('b');
        } else if (key === 'r') {
            this.resetApp();
        } else if (key === ' ') {
            e.preventDefault();
            this.togglePause();
        }
    },

    /**
     * Handle key up events
     */
    handleKeyUp(e) {
        const key = e.key.toLowerCase();

        if (key === 'a' || key === 'z') {
            this.releaseButton('a');
        } else if (key === 'b' || key === 'x') {
            this.releaseButton('b');
        }
    },

    /**
     * Press a button
     */
    pressButton(button) {
        if (this.buttons[button]) return; // Already pressed

        this.buttons[button] = true;

        const btnElement = button === 'a' ? this.elements.btnA : this.elements.btnB;
        btnElement.classList.add('pressed');

        // Call callback if registered
        if (button === 'a' && this.buttonCallbacks.onAPress) {
            this.buttonCallbacks.onAPress();
        } else if (button === 'b' && this.buttonCallbacks.onBPress) {
            this.buttonCallbacks.onBPress();
        }
    },

    /**
     * Release a button
     */
    releaseButton(button) {
        if (!this.buttons[button]) return; // Not pressed

        this.buttons[button] = false;

        const btnElement = button === 'a' ? this.elements.btnA : this.elements.btnB;
        btnElement.classList.remove('pressed');

        // Call callback if registered
        if (button === 'a' && this.buttonCallbacks.onARelease) {
            this.buttonCallbacks.onARelease();
        } else if (button === 'b' && this.buttonCallbacks.onBRelease) {
            this.buttonCallbacks.onBRelease();
        }
    },

    /**
     * Check if button A is pressed
     */
    isButtonAPressed() {
        return this.buttons.a;
    },

    /**
     * Check if button B is pressed
     */
    isButtonBPressed() {
        return this.buttons.b;
    },

    /**
     * Register button callbacks
     */
    onButtonA(pressCallback, releaseCallback) {
        this.buttonCallbacks.onAPress = pressCallback || null;
        this.buttonCallbacks.onARelease = releaseCallback || null;
    },

    onButtonB(pressCallback, releaseCallback) {
        this.buttonCallbacks.onBPress = pressCallback || null;
        this.buttonCallbacks.onBRelease = releaseCallback || null;
    },

    /**
     * Clear all button callbacks
     */
    clearButtonCallbacks() {
        this.buttonCallbacks.onAPress = null;
        this.buttonCallbacks.onARelease = null;
        this.buttonCallbacks.onBPress = null;
        this.buttonCallbacks.onBRelease = null;
    },

    // ========== Matrix Drawing API ==========

    /**
     * Clear the matrix (all LEDs off)
     */
    clearMatrix() {
        this.matrix = Array(8).fill(null).map(() => Array(8).fill(0));
    },

    /**
     * Set a single pixel
     * @param {number} x - X coordinate (0-7)
     * @param {number} y - Y coordinate (0-7)
     * @param {number|string} color - 0=off, 1=red, or color name ('red','green','blue','yellow')
     */
    setPixel(x, y, color = 1) {
        if (x >= 0 && x < 8 && y >= 0 && y < 8) {
            this.matrix[y][x] = color;
        }
    },

    /**
     * Get a pixel value
     */
    getPixel(x, y) {
        if (x >= 0 && x < 8 && y >= 0 && y < 8) {
            return this.matrix[y][x];
        }
        return 0;
    },

    /**
     * Toggle a pixel
     */
    togglePixel(x, y, color = 1) {
        if (x >= 0 && x < 8 && y >= 0 && y < 8) {
            this.matrix[y][x] = this.matrix[y][x] ? 0 : color;
        }
    },

    /**
     * Fill entire matrix with a color
     */
    fill(color = 1) {
        for (let y = 0; y < 8; y++) {
            for (let x = 0; x < 8; x++) {
                this.matrix[y][x] = color;
            }
        }
    },

    /**
     * Draw a line (Bresenham's algorithm)
     */
    drawLine(x0, y0, x1, y1, color = 1) {
        const dx = Math.abs(x1 - x0);
        const dy = Math.abs(y1 - y0);
        const sx = x0 < x1 ? 1 : -1;
        const sy = y0 < y1 ? 1 : -1;
        let err = dx - dy;

        while (true) {
            this.setPixel(x0, y0, color);

            if (x0 === x1 && y0 === y1) break;

            const e2 = 2 * err;
            if (e2 > -dy) {
                err -= dy;
                x0 += sx;
            }
            if (e2 < dx) {
                err += dx;
                y0 += sy;
            }
        }
    },

    /**
     * Draw a rectangle outline
     */
    drawRect(x, y, w, h, color = 1) {
        this.drawLine(x, y, x + w - 1, y, color);
        this.drawLine(x + w - 1, y, x + w - 1, y + h - 1, color);
        this.drawLine(x + w - 1, y + h - 1, x, y + h - 1, color);
        this.drawLine(x, y + h - 1, x, y, color);
    },

    /**
     * Draw a filled rectangle
     */
    fillRect(x, y, w, h, color = 1) {
        for (let py = y; py < y + h; py++) {
            for (let px = x; px < x + w; px++) {
                this.setPixel(px, py, color);
            }
        }
    },

    /**
     * Draw a circle outline
     */
    drawCircle(cx, cy, r, color = 1) {
        let x = r;
        let y = 0;
        let err = 0;

        while (x >= y) {
            this.setPixel(cx + x, cy + y, color);
            this.setPixel(cx + y, cy + x, color);
            this.setPixel(cx - y, cy + x, color);
            this.setPixel(cx - x, cy + y, color);
            this.setPixel(cx - x, cy - y, color);
            this.setPixel(cx - y, cy - x, color);
            this.setPixel(cx + y, cy - x, color);
            this.setPixel(cx + x, cy - y, color);

            y++;
            err += 1 + 2 * y;
            if (2 * (err - x) + 1 > 0) {
                x--;
                err += 1 - 2 * x;
            }
        }
    },

    /**
     * Draw a bitmap (array of rows)
     * @param {number[][]} bitmap - 2D array where 1=on, 0=off
     * @param {number} offsetX - X offset
     * @param {number} offsetY - Y offset
     * @param {number|string} color - Color for on pixels
     */
    drawBitmap(bitmap, offsetX = 0, offsetY = 0, color = 1) {
        for (let y = 0; y < bitmap.length; y++) {
            for (let x = 0; x < bitmap[y].length; x++) {
                if (bitmap[y][x]) {
                    this.setPixel(x + offsetX, y + offsetY, color);
                }
            }
        }
    },

    // ========== App Management ==========

    /**
     * Register an app
     * @param {string} name - App name
     * @param {object} app - App object with init(), update(), render() methods
     */
    registerApp(name, app) {
        this.apps[name] = app;
        this.updateAppSelector();
        this.log(`Registered app: ${name}`);
    },

    /**
     * Update the app selector dropdown
     */
    updateAppSelector() {
        if (!this.elements.appSelect) return;

        // Clear existing options (except first)
        while (this.elements.appSelect.options.length > 1) {
            this.elements.appSelect.remove(1);
        }

        // Add apps
        for (const name of Object.keys(this.apps)) {
            const option = document.createElement('option');
            option.value = name;
            option.textContent = name;
            this.elements.appSelect.appendChild(option);
        }
    },

    /**
     * Load and start an app
     */
    loadApp(name) {
        if (!name) {
            this.currentApp = null;
            this.elements.currentAppDisplay.textContent = 'None';
            this.clearMatrix();
            this.clearButtonCallbacks();
            this.log('No app loaded');
            return;
        }

        const app = this.apps[name];
        if (!app) {
            this.log(`App not found: ${name}`);
            return;
        }

        this.currentApp = app;
        this.frameCount = 0;
        this.clearMatrix();
        this.clearButtonCallbacks();

        // Initialize the app
        if (app.init) {
            app.init(this);
        }

        this.elements.currentAppDisplay.textContent = name;
        this.log(`Loaded app: ${name}`);
    },

    /**
     * Reset the current app
     */
    resetApp() {
        if (this.currentApp) {
            this.frameCount = 0;
            this.clearMatrix();
            this.clearButtonCallbacks();

            if (this.currentApp.init) {
                this.currentApp.init(this);
            }
            this.log('App reset');
        }
    },

    /**
     * Toggle pause
     */
    togglePause() {
        this.paused = !this.paused;
        this.log(this.paused ? 'Paused' : 'Resumed');
    },

    // ========== Game Loop ==========

    /**
     * Main game loop
     */
    gameLoop() {
        const now = performance.now();
        const delta = now - this.lastFrameTime;

        // Calculate FPS
        if (delta > 0) {
            this.fps = Math.round(1000 / delta);
        }

        // Update at target FPS
        if (delta >= 1000 / this.targetFPS) {
            this.lastFrameTime = now;

            if (!this.paused && this.currentApp) {
                // Update app logic
                if (this.currentApp.update) {
                    this.currentApp.update(this, delta / 1000);
                }

                // Render app
                if (this.currentApp.render) {
                    this.currentApp.render(this);
                }

                this.frameCount++;
            }

            // Render matrix to DOM
            this.renderMatrix();

            // Update UI
            this.elements.fpsDisplay.textContent = this.fps;
            this.elements.frameDisplay.textContent = this.frameCount;
        }

        requestAnimationFrame(() => this.gameLoop());
    },

    /**
     * Render the matrix state to DOM
     */
    renderMatrix() {
        for (let y = 0; y < 8; y++) {
            for (let x = 0; x < 8; x++) {
                const led = this.elements.leds[y * 8 + x];
                const value = this.matrix[y][x];

                // Remove all color classes
                led.classList.remove('on', 'green', 'blue', 'yellow');

                if (value) {
                    if (value === 1 || value === 'red') {
                        led.classList.add('on');
                    } else if (typeof value === 'string') {
                        led.classList.add(value);
                    } else {
                        led.classList.add('on');
                    }
                }
            }
        }
    },

    /**
     * Log a message to the status bar
     */
    log(message) {
        if (this.elements.statusBar) {
            this.elements.statusBar.textContent = message;
        }
        console.log(`[Simulator] ${message}`);
    },

    // ========== Utility Functions ==========

    /**
     * Get a random integer
     */
    random(min, max) {
        return Math.floor(Math.random() * (max - min + 1)) + min;
    },

    /**
     * Constrain a value to a range
     */
    constrain(value, min, max) {
        return Math.min(Math.max(value, min), max);
    }
};

// Export for use in apps
window.Simulator = Simulator;
