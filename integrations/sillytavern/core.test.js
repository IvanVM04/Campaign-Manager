import assert from "node:assert/strict";
import test from "node:test";

import {
    buildRetrievalQuery,
    findClarificationOrigin,
    selectClarificationChallenge,
} from "./core.js";


test(
    "buildRetrievalQuery combines configured query and player input",
    () => {
        const result = buildRetrievalQuery(
            "Estado actual de la campaña.",
            "Abro la puerta.",
        );

        assert.equal(
            result,
            [
                "Estado actual de la campaña.",
                "",
                "Acción actual del jugador:",
                "Abro la puerta.",
            ].join("\n"),
        );
    },
);


test(
    "buildRetrievalQuery trims both values",
    () => {
        const result = buildRetrievalQuery(
            "  Estado actual.  ",
            "  Abro la puerta.  ",
        );

        assert.equal(
            result,
            [
                "Estado actual.",
                "",
                "Acción actual del jugador:",
                "Abro la puerta.",
            ].join("\n"),
        );
    },
);


test(
    "buildRetrievalQuery returns empty string without configured query",
    () => {
        assert.equal(
            buildRetrievalQuery(
                "   ",
                "Abro la puerta.",
            ),
            "",
        );
    },
);


test(
    "buildRetrievalQuery returns empty string without player input",
    () => {
        assert.equal(
            buildRetrievalQuery(
                "Estado actual.",
                "   ",
            ),
            "",
        );
    },
);

test(
    'selectClarificationChallenge returns the active challenge for a new answer',
    () => {
        const result = selectClarificationChallenge(
            {
                has_clarification: true,
                lifecycle_state: 'awaiting_input',
                pending_clarification_id: '42:active-token',
                last_pending_clarification_id: null,
                last_answer: null,
            },
            'La puerta de roble.',
        );

        assert.deepEqual(result, {
            pendingClarificationId: '42:active-token',
            retry: false,
        });
    },
);


test(
    'selectClarificationChallenge retries the previously accepted answer before using a newer pending challenge',
    () => {
        const result = selectClarificationChallenge(
            {
                has_clarification: true,
                lifecycle_state: 'awaiting_input',
                pending_clarification_id: '42:next-token',
                last_pending_clarification_id: '42:previous-token',
                last_answer: 'La puerta de roble.',
            },
            'La puerta de roble.',
        );

        assert.deepEqual(result, {
            pendingClarificationId: '42:previous-token',
            retry: true,
        });
    },
);


test(
    'selectClarificationChallenge rejects unrelated input after clarification completion',
    () => {
        const result = selectClarificationChallenge(
            {
                has_clarification: true,
                lifecycle_state: 'completed',
                last_pending_clarification_id: '42:previous-token',
                last_answer: 'La puerta de roble.',
            },
            'Ahora busco la salida.',
        );

        assert.equal(result, null);
    },
);


test(
    'findClarificationOrigin finds the pending action behind one clarification exchange',
    async () => {
        const original = { is_user: true, mes: 'Abro una puerta.' };
        const question = { is_user: false, mes: '¿Qué puerta?' };
        const answer = { is_user: true, mes: 'La de roble.' };
        const states = new Map([
            ['turn-original', {
                has_clarification: true,
                lifecycle_state: 'awaiting_input',
                player_input: 'Abro una puerta.',
                pending_clarification_id: '42:second-question',
                last_pending_clarification_id: '42:first-question',
                last_answer: 'La de roble anterior.',
            }],
        ]);

        const result = await findClarificationOrigin(
            [original, question, answer],
            answer,
            'La de hierro.',
            'answer-two-turn',
            async (message) => message === original ? 'turn-original' : 'answer-turn',
            async (turnId) => states.get(turnId) ?? { has_clarification: false },
        );

        assert.equal(result.externalTurnId, 'turn-original');
        assert.equal(result.playerInput, 'Abro una puerta.');
        assert.equal(result.pendingClarificationId, '42:second-question');
        assert.equal(result.retry, false);
    },
);


test(
    'findClarificationOrigin replays the previous challenge when an accepted answer is retried',
    async () => {
        const original = { is_user: true, mes: 'Abro una puerta.' };
        const firstQuestion = { is_user: false, mes: '¿Qué puerta?' };
        const firstAnswer = { is_user: true, mes: 'La de roble.' };
        const secondQuestion = { is_user: false, mes: '¿Con cuidado?' };
        const retryAnswer = { is_user: true, mes: 'La de roble.' };
        const state = {
            has_clarification: true,
            lifecycle_state: 'awaiting_input',
            player_input: 'Abro una puerta.',
            pending_clarification_id: '42:second-question',
            last_pending_clarification_id: '42:first-question',
            last_answer: 'La de roble.',
            last_answer_external_turn_id: 'retry-answer-turn',
        };

        const result = await findClarificationOrigin(
            [original, firstQuestion, firstAnswer, secondQuestion, retryAnswer],
            retryAnswer,
            'La de roble.',
            'retry-answer-turn',
            async (message) => message === original ? 'turn-original' : 'unrelated-turn',
            async (turnId) => turnId === 'turn-original'
                ? state
                : { has_clarification: false },
        );

        assert.equal(result.pendingClarificationId, '42:first-question');
        assert.equal(result.retry, true);
    },
);


test(
    'findClarificationOrigin does not mistake a new turn for a repeated clarification answer',
    async () => {
        const original = { is_user: true, mes: 'Abro una puerta.' };
        const question = { is_user: false, mes: '¿Qué puerta?' };
        const answer = { is_user: true, mes: 'La de roble.' };
        const narrative = { is_user: false, mes: 'La puerta de roble se abre.' };
        const newAction = { is_user: true, mes: 'La de roble.' };
        const state = {
            has_clarification: true,
            lifecycle_state: 'completed',
            player_input: 'Abro una puerta.',
            last_pending_clarification_id: '42:first-question',
            last_answer: 'La de roble.',
            last_answer_external_turn_id: 'new-action-turn',
            narrative: 'La puerta de roble se abre.',
        };

        const result = await findClarificationOrigin(
            [original, question, answer, narrative, newAction],
            newAction,
            'La de roble.',
            'new-action-turn',
            async (message) => message === original ? 'turn-original' : 'unrelated-turn',
            async (turnId) => turnId === 'turn-original'
                ? state
                : { has_clarification: false },
        );

        assert.equal(result, null);
    },
);


test(
    'selectClarificationChallenge permits retry recovery while a planning lease is present',
    () => {
        const result = selectClarificationChallenge(
            {
                has_clarification: true,
                lifecycle_state: 'planning',
                pending_clarification_id: '42:active-token',
                last_pending_clarification_id: null,
                last_answer: null,
            },
            'La puerta de roble.',
        );

        assert.deepEqual(result, {
            pendingClarificationId: '42:active-token',
            retry: false,
        });
    },
);


test(
    'findClarificationOrigin follows several rounds back to the original action',
    async () => {
        const original = { is_user: true, mes: 'Abro una puerta.' };
        const questionOne = { is_user: false, mes: '¿Qué puerta?' };
        const answerOne = { is_user: true, mes: 'La de roble.' };
        const questionTwo = { is_user: false, mes: '¿La abres con cuidado?' };
        const answerTwo = { is_user: true, mes: 'Con cuidado.' };
        const state = {
            has_clarification: true,
            lifecycle_state: 'awaiting_input',
            player_input: 'Abro una puerta.',
            pending_clarification_id: '42:third-question',
            last_pending_clarification_id: '42:second-question',
            last_answer: 'La de roble.',
            last_answer_external_turn_id: 'answer-one-turn',
        };

        const result = await findClarificationOrigin(
            [original, questionOne, answerOne, questionTwo, answerTwo],
            answerTwo,
            'Con cuidado.',
            'answer-two-turn',
            async (message) => message === original ? 'turn-original' : 'answer-turn',
            async (turnId) => turnId === 'turn-original'
                ? state
                : { has_clarification: false },
        );

        assert.equal(result.externalTurnId, 'turn-original');
        assert.equal(result.pendingClarificationId, '42:third-question');
        assert.equal(result.retry, false);
    },
);


test(
    'selectClarificationChallenge uses the active challenge when identical text comes from a new message',
    () => {
        const result = selectClarificationChallenge(
            {
                has_clarification: true,
                lifecycle_state: 'awaiting_input',
                pending_clarification_id: '42:active-token',
                last_pending_clarification_id: '42:previous-token',
                last_answer: 'Sí.',
                last_answer_external_turn_id: 'message-previous',
            },
            'Sí.',
            'message-current',
        );

        assert.deepEqual(result, {
            pendingClarificationId: '42:active-token',
            retry: false,
        });
    },
);
