import assert from "node:assert/strict";
import test from "node:test";

import {
    buildRetrievalQuery,
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
