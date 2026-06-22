
    document.addEventListener('alpine:init', () => {
        Alpine.data('activityForm', () => ({
            questions: [],
            questionsJsonPayload: '',
            equationModal: { open: false, questionIndex: null, latex: '', display: 'block' },

            init() {
                this.rootEl = this.$el || document.querySelector('[x-data="activityForm()"]');
                const dataEl = document.getElementById('questions-data');
                const rawQuestions = dataEl ? JSON.parse(dataEl.textContent || '[]') : [];
                this.questions = rawQuestions.map((question) => this.normalizeQuestion(question));
                this.questionsJsonPayload = JSON.stringify(this.serializeQuestions());
                this.$nextTick(() => this.typesetMath(document));
            },

            get totalPoints() {
                const total = this.questions.reduce((sum, question) => sum + (parseFloat(question.points) || 0), 0);
                return this.formatNumber(total);
            },

            normalizeQuestion(question) {
                const uid = question.uid || this.newUid('question');
                const choices = this.normalizeChoices(question.choices || []);
                const correctAnswers = Array.isArray(question.correct_answers) ? question.correct_answers : (question.correct_answer ? [question.correct_answer] : []);
                const content = question.content || { html: question.text || '', plain_text: '' };
                const settings = question.answer_settings || {};
                return {
                    uid,
                    text: question.text || '',
                    content: {
                        html: content.html || question.text || '',
                        plain_text: content.plain_text || ''
                    },
                    type: question.type || 'multiple_choice',
                    points: question.points || 1,
                    choices: choices.length ? choices : this.defaultChoices(),
                    correct_answers: correctAnswers,
                    tolerance_percent: settings.tolerance_percent || 0
                };
            },

            normalizeChoices(choices) {
                return choices.map((choice, index) => {
                    if (typeof choice === 'string') {
                        return { id: this.newUid('choice'), label: this.choiceLetter(index), text: choice };
                    }
                    return {
                        id: choice.id || this.newUid('choice'),
                        label: choice.label || this.choiceLetter(index),
                        text: choice.text || ''
                    };
                });
            },

            defaultChoices() {
                return ['Choice A', 'Choice B', 'Choice C', 'Choice D'].map((text, index) => ({
                    id: this.newUid('choice'),
                    label: this.choiceLetter(index),
                    text
                }));
            },

            addQuestion() {
                const choices = this.defaultChoices();
                this.questions.push({
                    uid: this.newUid('question'),
                    text: '',
                    content: { html: '', plain_text: '' },
                    type: 'multiple_choice',
                    points: 1,
                    choices,
                    correct_answers: [],
                    tolerance_percent: 0
                });
            },

            removeQuestion(index) {
                this.questions.splice(index, 1);
            },

            addChoice(question) {
                question.choices.push({
                    id: this.newUid('choice'),
                    label: this.choiceLetter(question.choices.length),
                    text: `Choice ${this.choiceLetter(question.choices.length)}`
                });
            },

            removeChoice(question, index) {
                const [removed] = question.choices.splice(index, 1);
                question.correct_answers = question.correct_answers.filter((answer) => answer !== removed.id);
            },

            handleTypeChange(question) {
                if (question.type === 'multiple_choice') {
                    if (!question.choices.length) {
                        question.choices = this.defaultChoices();
                    }
                    question.correct_answers = question.correct_answers.filter((answer) => question.choices.some((choice) => choice.id === answer));
                    return;
                }
                if (question.type === 'true_false') {
                    question.correct_answers = [question.correct_answers[0] === 'False' ? 'False' : 'True'];
                    return;
                }
                if (!question.correct_answers.length) {
                    question.correct_answers = [''];
                }
            },

            editorHtml(question) {
                return question.content.html || this.escapeHtml(question.text || '');
            },

            getCleanHtml(editor) {
                const clone = editor.cloneNode(true);
                const mathNodes = clone.querySelectorAll('.math-expression, .math-block');
                mathNodes.forEach(node => {
                    const latex = node.dataset.latex || '';
                    const isBlock = node.dataset.display === 'block';
                    node.innerHTML = '';
                    node.textContent = isBlock ? `\\[${latex}\\]` : `\\(${latex}\\)`;
                });
                return clone.innerHTML;
            },

            syncEditor(question, editor) {
                question.content.html = this.getCleanHtml(editor);
                question.content.plain_text = editor.innerText.trim();
                question.text = question.content.plain_text;
            },

            formatEditor(index, command) {
                this.focusEditor(index);
                document.execCommand(command, false, null);
                const question = this.questions[index];
                const editor = this.editorForQuestion(question);
                if (editor) {
                    this.syncEditor(question, editor);
                }
            },

            focusEditor(index) {
                const editor = this.editorForQuestion(this.questions[index]);
                if (editor) {
                    editor.focus();
                }
            },

            editorForQuestion(question) {
                return question ? document.getElementById('question-editor-' + question.uid) : null;
            },

            openEquation(index) {
                this.equationModal = { open: true, questionIndex: index, latex: '', display: 'block' };
                this.$nextTick(() => {
                    const mf = document.getElementById('math-live-editor');
                    if (mf) mf.value = '';
                    this.renderEquationPreview();
                });
            },

            equationPreviewText() {
                const latex = this.equationModal.latex || '';
                return this.equationModal.display === 'block' ? `\\[${latex}\\]` : `\\(${latex}\\)`;
            },

            renderEquationPreview() {
                this.$nextTick(() => {
                    if (this.$refs.equationPreview) {
                        this.$refs.equationPreview.textContent = this.equationPreviewText();
                        this.typesetMath(this.$refs.equationPreview);
                    }
                });
            },

            insertEquation() {
                const question = this.questions[this.equationModal.questionIndex];
                const editor = this.editorForQuestion(question);
                const latex = (this.equationModal.latex || '').trim();
                if (!question || !editor || !latex) {
                    return;
                }
                const isBlock = this.equationModal.display === 'block';
                const node = document.createElement(isBlock ? 'div' : 'span');
                node.className = isBlock ? 'math-block' : 'math-expression';
                node.dataset.display = isBlock ? 'block' : 'inline';
                node.dataset.latex = latex;
                node.textContent = isBlock ? `\\[${latex}\\]` : `\\(${latex}\\)`;
                this.insertNodeIntoEditor(editor, node);
                this.syncEditor(question, editor);
                this.equationModal.open = false;
                this.$nextTick(() => {
                    if (typeof window.MathJax !== 'undefined' && window.MathJax.typesetPromise) {
                        window.MathJax.typesetPromise([editor]).catch((err) => console.error(err));
                    } else {
                        this.typesetMath(editor);
                    }
                });
            },

            async insertImage(question, index, event) {
                const file = event.target.files && event.target.files[0];
                event.target.value = '';
                if (!file) {
                    return;
                }
                const editor = this.editorForQuestion(question);
                const src = await this.imageFileToDataUrl(file);
                const imageId = this.newUid('image');
                
                const wrapper = document.createElement('span');
                wrapper.contentEditable = 'false';
                wrapper.className = 'image-resize-wrapper inline-block resize overflow-hidden border border-gray-200 rounded-md relative group align-top bg-gray-50';
                wrapper.style.width = '300px';
                wrapper.style.minWidth = '50px';
                wrapper.style.minHeight = '50px';
                wrapper.style.maxWidth = '100%';

                const img = document.createElement('img');
                img.src = src;
                img.alt = file.name || 'Question image';
                img.className = 'question-image w-full h-full object-contain pointer-events-none';
                img.dataset.imageId = imageId;
                
                const deleteBtn = document.createElement('button');
                deleteBtn.type = 'button';
                deleteBtn.className = 'absolute top-1 right-1 bg-red-500 text-white rounded p-1 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center pointer-events-auto';
                deleteBtn.innerHTML = '<i class="bi bi-trash"></i>';
                deleteBtn.title = 'Remove Image';
                deleteBtn.onclick = (e) => {
                    e.preventDefault();
                    wrapper.remove();
                    editor.dispatchEvent(new Event('input', { bubbles: true }));
                };

                wrapper.appendChild(img);
                wrapper.appendChild(deleteBtn);
                
                this.insertNodeIntoEditor(editor, wrapper);
                this.syncEditor(question, editor);
            },

            imageFileToDataUrl(file) {
                return new Promise((resolve) => {
                    const reader = new FileReader();
                    reader.onload = () => {
                        const image = new Image();
                        image.onload = () => {
                            const maxSide = 1400;
                            const scale = Math.min(1, maxSide / Math.max(image.width, image.height));
                            const canvas = document.createElement('canvas');
                            canvas.width = Math.round(image.width * scale);
                            canvas.height = Math.round(image.height * scale);
                            const ctx = canvas.getContext('2d');
                            ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
                            resolve(canvas.toDataURL('image/jpeg', 0.88));
                        };
                        image.src = reader.result;
                    };
                    reader.readAsDataURL(file);
                });
            },

            insertNodeIntoEditor(editor, node) {
                editor.focus();
                const selection = window.getSelection();
                if (selection && selection.rangeCount) {
                    const range = selection.getRangeAt(0);
                    if (editor.contains(range.commonAncestorContainer)) {
                        range.deleteContents();
                        range.insertNode(node);
                        range.setStartAfter(node);
                        range.setEndAfter(node);
                        selection.removeAllRanges();
                        selection.addRange(range);
                        return;
                    }
                }
                editor.appendChild(node);
            },

            acceptedRangeText(question) {
                const answer = parseFloat(question.correct_answers[0]);
                const tolerance = parseFloat(question.tolerance_percent) || 0;
                if (!Number.isFinite(answer)) {
                    return 'Set a numeric answer';
                }
                const offset = Math.abs(answer) * tolerance / 100;
                return `${this.formatNumber(answer - offset)} to ${this.formatNumber(answer + offset)}`;
            },

            serializeQuestions() {
                return this.questions.map((question) => {
                    const choices = question.choices.map((choice, index) => ({
                        id: choice.id,
                        label: this.choiceLetter(index),
                        text: choice.text
                    }));
                    const correctAnswers = Array.isArray(question.correct_answers) ? question.correct_answers.filter((answer) => answer !== null && answer !== undefined && String(answer).trim() !== '') : [];
                    const payload = {
                        text: question.text || question.content.plain_text || '',
                        content: question.content,
                        type: question.type,
                        points: question.points || 0,
                        choices: question.type === 'multiple_choice' ? choices : [],
                        correct_answers: correctAnswers,
                        correct_answer: correctAnswers.join(', ')
                    };
                    if (question.type === 'number') {
                        payload.tolerance_percent = question.tolerance_percent || 0;
                    }
                    return payload;
                });
            },

            submitForm() {
                this.questions.forEach((question) => {
                    const editor = this.editorForQuestion(question);
                    if (editor) {
                        this.syncEditor(question, editor);
                    }
                });
                this.questionsJsonPayload = JSON.stringify(this.serializeQuestions());
            },

            typesetMath(target) {
                if (window.MathJax && window.MathJax.typesetPromise) {
                    window.MathJax.typesetPromise([target]).catch(() => {});
                }
            },

            choiceLetter(index) {
                return String.fromCharCode(65 + index);
            },

            newUid(prefix) {
                return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
            },

            formatNumber(value) {
                const number = Number(value);
                if (!Number.isFinite(number)) {
                    return '0';
                }
                return number.toFixed(4).replace(/\.?0+$/, '');
            },

            escapeHtml(value) {
                const div = document.createElement('div');
                div.textContent = value;
                return div.innerHTML;
            }
        }));
    });
