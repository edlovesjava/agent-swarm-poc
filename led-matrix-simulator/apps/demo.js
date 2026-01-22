/**
 * Demo Apps for LED Matrix Simulator
 * These demonstrate the API and serve as templates for new apps
 */

// ========== SNAKE GAME ==========
Simulator.registerApp('Snake', {
    snake: [],
    direction: { x: 1, y: 0 },
    nextDirection: { x: 1, y: 0 },
    food: { x: 0, y: 0 },
    gameOver: false,
    score: 0,
    moveTimer: 0,
    moveInterval: 0.15, // seconds between moves

    init(sim) {
        // Start in the middle
        this.snake = [
            { x: 4, y: 4 },
            { x: 3, y: 4 },
            { x: 2, y: 4 }
        ];
        this.direction = { x: 1, y: 0 };
        this.nextDirection = { x: 1, y: 0 };
        this.gameOver = false;
        this.score = 0;
        this.moveTimer = 0;
        this.spawnFood(sim);

        // Button A: Turn left (counterclockwise)
        sim.onButtonA(() => {
            if (this.gameOver) {
                this.init(sim);
                return;
            }
            // Rotate direction counterclockwise
            const newDir = { x: this.direction.y, y: -this.direction.x };
            if (newDir.x !== -this.direction.x || newDir.y !== -this.direction.y) {
                this.nextDirection = newDir;
            }
        });

        // Button B: Turn right (clockwise)
        sim.onButtonB(() => {
            if (this.gameOver) {
                this.init(sim);
                return;
            }
            // Rotate direction clockwise
            const newDir = { x: -this.direction.y, y: this.direction.x };
            if (newDir.x !== -this.direction.x || newDir.y !== -this.direction.y) {
                this.nextDirection = newDir;
            }
        });

        sim.log('Snake: BTN A=Left, BTN B=Right');
    },

    spawnFood(sim) {
        do {
            this.food.x = sim.random(0, 7);
            this.food.y = sim.random(0, 7);
        } while (this.snake.some(s => s.x === this.food.x && s.y === this.food.y));
    },

    update(sim, dt) {
        if (this.gameOver) return;

        this.moveTimer += dt;
        if (this.moveTimer < this.moveInterval) return;
        this.moveTimer = 0;

        // Apply direction change
        this.direction = { ...this.nextDirection };

        // Calculate new head position
        const head = this.snake[0];
        const newHead = {
            x: (head.x + this.direction.x + 8) % 8,
            y: (head.y + this.direction.y + 8) % 8
        };

        // Check self collision
        if (this.snake.some(s => s.x === newHead.x && s.y === newHead.y)) {
            this.gameOver = true;
            sim.log(`Game Over! Score: ${this.score}`);
            return;
        }

        // Add new head
        this.snake.unshift(newHead);

        // Check food collision
        if (newHead.x === this.food.x && newHead.y === this.food.y) {
            this.score++;
            this.spawnFood(sim);
            // Speed up slightly
            this.moveInterval = Math.max(0.08, this.moveInterval - 0.005);
        } else {
            // Remove tail
            this.snake.pop();
        }
    },

    render(sim) {
        sim.clearMatrix();

        if (this.gameOver) {
            // Flash the screen
            if (Math.floor(sim.frameCount / 10) % 2 === 0) {
                sim.fill('red');
            }
            return;
        }

        // Draw food (blinking)
        if (sim.frameCount % 10 < 7) {
            sim.setPixel(this.food.x, this.food.y, 'green');
        }

        // Draw snake
        this.snake.forEach((segment, i) => {
            sim.setPixel(segment.x, segment.y, i === 0 ? 'yellow' : 'red');
        });
    }
});


// ========== PONG GAME ==========
Simulator.registerApp('Pong', {
    paddle: { y: 3, height: 3 },
    ball: { x: 4, y: 4, vx: 1, vy: 0.5 },
    score: 0,
    gameOver: false,

    init(sim) {
        this.paddle = { y: 3, height: 3 };
        this.ball = { x: 4, y: 4, vx: 0.15, vy: 0.1 };
        this.score = 0;
        this.gameOver = false;

        sim.onButtonA(() => {
            if (this.gameOver) {
                this.init(sim);
                return;
            }
            this.paddle.y = sim.constrain(this.paddle.y - 1, 0, 8 - this.paddle.height);
        });

        sim.onButtonB(() => {
            if (this.gameOver) {
                this.init(sim);
                return;
            }
            this.paddle.y = sim.constrain(this.paddle.y + 1, 0, 8 - this.paddle.height);
        });

        sim.log('Pong: BTN A=Up, BTN B=Down');
    },

    update(sim, dt) {
        if (this.gameOver) return;

        // Move ball
        this.ball.x += this.ball.vx;
        this.ball.y += this.ball.vy;

        // Bounce off top/bottom
        if (this.ball.y <= 0 || this.ball.y >= 7) {
            this.ball.vy = -this.ball.vy;
            this.ball.y = sim.constrain(this.ball.y, 0, 7);
        }

        // Bounce off right wall
        if (this.ball.x >= 7) {
            this.ball.vx = -Math.abs(this.ball.vx);
        }

        // Check paddle collision (left side)
        if (this.ball.x <= 1) {
            const ballY = Math.round(this.ball.y);
            if (ballY >= this.paddle.y && ballY < this.paddle.y + this.paddle.height) {
                this.ball.vx = Math.abs(this.ball.vx) * 1.05; // Speed up
                this.ball.vy += (ballY - (this.paddle.y + 1)) * 0.05;
                this.score++;
                sim.log(`Score: ${this.score}`);
            } else if (this.ball.x <= 0) {
                this.gameOver = true;
                sim.log(`Game Over! Final Score: ${this.score}`);
            }
        }
    },

    render(sim) {
        sim.clearMatrix();

        if (this.gameOver) {
            if (Math.floor(sim.frameCount / 10) % 2 === 0) {
                sim.fill('red');
            }
            return;
        }

        // Draw paddle
        for (let i = 0; i < this.paddle.height; i++) {
            sim.setPixel(0, this.paddle.y + i, 'blue');
        }

        // Draw ball
        sim.setPixel(Math.round(this.ball.x), Math.round(this.ball.y), 'yellow');
    }
});


// ========== BREAKOUT GAME ==========
Simulator.registerApp('Breakout', {
    paddle: { x: 3, width: 3 },
    ball: { x: 4, y: 5, vx: 0.12, vy: -0.12 },
    bricks: [],
    gameOver: false,
    won: false,

    init(sim) {
        this.paddle = { x: 3, width: 3 };
        this.ball = { x: 4, y: 5, vx: 0.12, vy: -0.12 };
        this.gameOver = false;
        this.won = false;

        // Create bricks (top 3 rows)
        this.bricks = [];
        for (let y = 0; y < 3; y++) {
            for (let x = 0; x < 8; x++) {
                this.bricks.push({ x, y, alive: true });
            }
        }

        sim.onButtonA(() => {
            if (this.gameOver || this.won) {
                this.init(sim);
                return;
            }
            this.paddle.x = sim.constrain(this.paddle.x - 1, 0, 8 - this.paddle.width);
        });

        sim.onButtonB(() => {
            if (this.gameOver || this.won) {
                this.init(sim);
                return;
            }
            this.paddle.x = sim.constrain(this.paddle.x + 1, 0, 8 - this.paddle.width);
        });

        sim.log('Breakout: BTN A=Left, BTN B=Right');
    },

    update(sim, dt) {
        if (this.gameOver || this.won) return;

        // Move ball
        this.ball.x += this.ball.vx;
        this.ball.y += this.ball.vy;

        // Bounce off walls
        if (this.ball.x <= 0 || this.ball.x >= 7) {
            this.ball.vx = -this.ball.vx;
        }
        if (this.ball.y <= 0) {
            this.ball.vy = -this.ball.vy;
        }

        // Check paddle collision
        if (this.ball.y >= 6.5) {
            const ballX = Math.round(this.ball.x);
            if (ballX >= this.paddle.x && ballX < this.paddle.x + this.paddle.width) {
                this.ball.vy = -Math.abs(this.ball.vy);
                this.ball.vx += (ballX - (this.paddle.x + 1)) * 0.03;
            } else if (this.ball.y >= 7.5) {
                this.gameOver = true;
                sim.log('Game Over!');
            }
        }

        // Check brick collisions
        const ballX = Math.round(this.ball.x);
        const ballY = Math.round(this.ball.y);
        for (const brick of this.bricks) {
            if (brick.alive && brick.x === ballX && brick.y === ballY) {
                brick.alive = false;
                this.ball.vy = -this.ball.vy;
                break;
            }
        }

        // Check win
        if (this.bricks.every(b => !b.alive)) {
            this.won = true;
            sim.log('You Win!');
        }
    },

    render(sim) {
        sim.clearMatrix();

        if (this.gameOver) {
            if (Math.floor(sim.frameCount / 10) % 2 === 0) {
                sim.fill('red');
            }
            return;
        }

        if (this.won) {
            if (Math.floor(sim.frameCount / 10) % 2 === 0) {
                sim.fill('green');
            }
            return;
        }

        // Draw bricks
        const colors = ['red', 'yellow', 'green'];
        for (const brick of this.bricks) {
            if (brick.alive) {
                sim.setPixel(brick.x, brick.y, colors[brick.y]);
            }
        }

        // Draw paddle
        for (let i = 0; i < this.paddle.width; i++) {
            sim.setPixel(this.paddle.x + i, 7, 'blue');
        }

        // Draw ball
        sim.setPixel(Math.round(this.ball.x), Math.round(this.ball.y), 'yellow');
    }
});


// ========== DRAWING PAD ==========
Simulator.registerApp('Drawing Pad', {
    cursor: { x: 4, y: 4 },
    drawing: [],
    penDown: false,

    init(sim) {
        this.cursor = { x: 4, y: 4 };
        this.drawing = Array(8).fill(null).map(() => Array(8).fill(0));
        this.penDown = false;

        let moveTimer = 0;
        const moveInterval = 0.1;

        // Store original update to handle cursor movement
        this._moveTimer = 0;

        // Button A: Toggle pen / move cursor based on hold
        sim.onButtonA(
            () => { this.penDown = !this.penDown; },
            null
        );

        // Button B while held: Clear all
        sim.onButtonB(
            () => {
                this.drawing = Array(8).fill(null).map(() => Array(8).fill(0));
                sim.log('Canvas cleared');
            },
            null
        );

        sim.log('Drawing: A=Toggle Pen, B=Clear, Hold A/B+move');
    },

    update(sim, dt) {
        this._moveTimer += dt;
        if (this._moveTimer < 0.12) return;

        // Move cursor based on button combinations
        if (sim.isButtonAPressed() && sim.isButtonBPressed()) {
            // Both buttons: move right
            this.cursor.x = (this.cursor.x + 1) % 8;
            this._moveTimer = 0;
        } else if (sim.isButtonAPressed()) {
            // A only: move up
            this.cursor.y = (this.cursor.y - 1 + 8) % 8;
            this._moveTimer = 0;
        } else if (sim.isButtonBPressed()) {
            // B only: move down
            this.cursor.y = (this.cursor.y + 1) % 8;
            this._moveTimer = 0;
        }

        // Draw if pen is down
        if (this.penDown) {
            this.drawing[this.cursor.y][this.cursor.x] = 1;
        }
    },

    render(sim) {
        sim.clearMatrix();

        // Draw the drawing
        for (let y = 0; y < 8; y++) {
            for (let x = 0; x < 8; x++) {
                if (this.drawing[y][x]) {
                    sim.setPixel(x, y, 'green');
                }
            }
        }

        // Draw cursor (blinking)
        if (sim.frameCount % 10 < 6) {
            sim.setPixel(this.cursor.x, this.cursor.y, this.penDown ? 'red' : 'yellow');
        }
    }
});


// ========== ANIMATION DEMO ==========
Simulator.registerApp('Animation Demo', {
    mode: 0,
    modes: ['spinner', 'pulse', 'rain', 'wave'],
    frame: 0,

    init(sim) {
        this.mode = 0;
        this.frame = 0;

        sim.onButtonA(() => {
            this.mode = (this.mode - 1 + this.modes.length) % this.modes.length;
            sim.log(`Mode: ${this.modes[this.mode]}`);
        });

        sim.onButtonB(() => {
            this.mode = (this.mode + 1) % this.modes.length;
            sim.log(`Mode: ${this.modes[this.mode]}`);
        });

        sim.log('Animation: BTN A/B to change mode');
    },

    update(sim, dt) {
        this.frame++;
    },

    render(sim) {
        sim.clearMatrix();

        switch (this.modes[this.mode]) {
            case 'spinner':
                this.renderSpinner(sim);
                break;
            case 'pulse':
                this.renderPulse(sim);
                break;
            case 'rain':
                this.renderRain(sim);
                break;
            case 'wave':
                this.renderWave(sim);
                break;
        }
    },

    renderSpinner(sim) {
        const angle = (this.frame * 0.1) % (Math.PI * 2);
        const cx = 3.5, cy = 3.5;
        for (let i = 0; i < 8; i++) {
            const a = angle + (i * Math.PI / 4);
            const r = 3;
            const x = Math.round(cx + Math.cos(a) * r);
            const y = Math.round(cy + Math.sin(a) * r);
            const colors = ['red', 'yellow', 'green', 'blue'];
            sim.setPixel(x, y, colors[i % 4]);
        }
    },

    renderPulse(sim) {
        const radius = Math.abs(Math.sin(this.frame * 0.05)) * 4;
        sim.drawCircle(4, 4, Math.round(radius), 'red');
    },

    renderRain(sim) {
        for (let x = 0; x < 8; x++) {
            const y = (this.frame + x * 3) % 12;
            if (y < 8) {
                sim.setPixel(x, y, 'blue');
            }
        }
    },

    renderWave(sim) {
        for (let x = 0; x < 8; x++) {
            const y = Math.round(3.5 + Math.sin((x + this.frame * 0.1) * 0.8) * 3);
            sim.setPixel(x, y, 'green');
        }
    }
});

console.log('Demo apps loaded!');
