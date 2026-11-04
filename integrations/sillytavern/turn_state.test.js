import test from 'node:test';
import assert from 'node:assert/strict';

import {
    buildStableTurnIdentityInput,
    TurnState,
} from './core.js';


function missingTurn() {
    return {
        exists: false,
        active_version: 0,
        narrative: null,
    };
}


test(
    'first generation uses version one',
    async () => {
        const state =
            new TurnState();

        const version =
            await state.getVersion(
                'turn-1',
                'La taberna está en silencio.',
                async () => missingTurn(),
            );

        assert.equal(
            version,
            1,
        );
    },
);


test(
    'same narrative keeps the same version',
    async () => {
        const state =
            new TurnState();

        const getPersistedState =
            async () => missingTurn();

        const firstVersion =
            await state.getVersion(
                'turn-1',
                'La taberna está en silencio.',
                getPersistedState,
            );

        const secondVersion =
            await state.getVersion(
                'turn-1',
                'La taberna está en silencio.',
                getPersistedState,
            );

        assert.equal(
            firstVersion,
            1,
        );

        assert.equal(
            secondVersion,
            1,
        );
    },
);


test(
    'same turn version cannot be processed twice locally',
    async () => {
        const state =
            new TurnState();

        const version =
            await state.getVersion(
                'turn-1',
                'La taberna está en silencio.',
                async () => missingTurn(),
            );

        assert.equal(
            state.tryMarkProcessing(
                'turn-1',
                version,
            ),
            true,
        );

        assert.equal(
            state.tryMarkProcessing(
                'turn-1',
                version,
            ),
            false,
        );
    },
);


test(
    'first regeneration increments version to two',
    async () => {
        const state =
            new TurnState();

        await state.getVersion(
            'turn-1',
            'Primera respuesta.',
            async () => missingTurn(),
        );

        const version =
            await state.getVersion(
                'turn-1',
                'Respuesta regenerada.',
                async () => {
                    throw new Error(
                        'backend should not be queried twice',
                    );
                },
            );

        assert.equal(
            version,
            2,
        );
    },
);


test(
    'second regeneration increments version to three',
    async () => {
        const state =
            new TurnState();

        await state.getVersion(
            'turn-1',
            'Primera respuesta.',
            async () => missingTurn(),
        );

        await state.getVersion(
            'turn-1',
            'Segunda respuesta.',
            async () => {
                throw new Error(
                    'backend should not be queried twice',
                );
            },
        );

        const version =
            await state.getVersion(
                'turn-1',
                'Tercera respuesta.',
                async () => {
                    throw new Error(
                        'backend should not be queried twice',
                    );
                },
            );

        assert.equal(
            version,
            3,
        );
    },
);


test(
    'backend failure allows retrying the same version',
    async () => {
        const state =
            new TurnState();

        const version =
            await state.getVersion(
                'turn-1',
                'La puerta se abre.',
                async () => missingTurn(),
            );

        assert.equal(
            version,
            1,
        );

        assert.equal(
            state.tryMarkProcessing(
                'turn-1',
                version,
            ),
            true,
        );

        state.markFailed(
            'turn-1',
            version,
        );

        const retryVersion =
            await state.getVersion(
                'turn-1',
                'La puerta se abre.',
                async () => {
                    throw new Error(
                        'backend should not be queried again',
                    );
                },
            );

        assert.equal(
            retryVersion,
            1,
        );

        assert.equal(
            state.tryMarkProcessing(
                'turn-1',
                retryVersion,
            ),
            true,
        );
    },
);


test(
    'persisted active narrative keeps persisted version',
    async () => {
        const state =
            new TurnState();

        const version =
            await state.getVersion(
                'turn-existing',
                'Narrativa persistida.',
                async () => ({
                    exists: true,
                    active_version: 4,
                    narrative:
                        'Narrativa persistida.',
                }),
            );

        assert.equal(
            version,
            4,
        );
    },
);


test(
    'new narrative after persisted turn increments active version',
    async () => {
        const state =
            new TurnState();

        const version =
            await state.getVersion(
                'turn-existing',
                'Nueva regeneración.',
                async () => ({
                    exists: true,
                    active_version: 4,
                    narrative:
                        'Narrativa anterior.',
                }),
            );

        assert.equal(
            version,
            5,
        );
    },
);


test(
    'reset starts a new local version sequence',
    async () => {
        const state =
            new TurnState();

        await state.getVersion(
            'turn-old',
            'Primera narrativa.',
            async () => missingTurn(),
        );

        await state.getVersion(
            'turn-old',
            'Segunda narrativa.',
            async () => {
                throw new Error(
                    'unexpected backend query',
                );
            },
        );

        state.reset();

        const version =
            await state.getVersion(
                'turn-new',
                'Narrativa del nuevo chat.',
                async () => missingTurn(),
            );

        assert.equal(
            version,
            1,
        );
    },
);


test(
    'different chats produce different stable turn identity inputs',
    () => {
        const firstChat =
            buildStableTurnIdentityInput(
                'chat-a',
                6,
            );

        const secondChat =
            buildStableTurnIdentityInput(
                'chat-b',
                6,
            );

        assert.notEqual(
            firstChat,
            secondChat,
        );
    },
);


test(
    'same chat and player message index produce stable identity input',
    () => {
        const first =
            buildStableTurnIdentityInput(
                'chat-a',
                6,
            );

        const second =
            buildStableTurnIdentityInput(
                'chat-a',
                6,
            );

        assert.equal(
            first,
            second,
        );
    },
);

test(
    'failed version is reused when regeneration produces a new narrative',
    async () => {
        const state =
            new TurnState();

        const firstVersion =
            await state.getVersion(
                'turn-1',
                'Primera respuesta.',
                async () => missingTurn(),
            );

        assert.equal(
            firstVersion,
            1,
        );

        assert.equal(
            state.tryMarkProcessing(
                'turn-1',
                firstVersion,
            ),
            true,
        );

        state.markFailed(
            'turn-1',
            firstVersion,
        );

        const retryVersion =
            await state.getVersion(
                'turn-1',
                'Nueva respuesta regenerada.',
                async () => {
                    throw new Error(
                        'backend should not be queried again',
                    );
                },
            );

        assert.equal(
            retryVersion,
            1,
        );

        assert.equal(
            state.tryMarkProcessing(
                'turn-1',
                retryVersion,
            ),
            true,
        );

        const nextVersion =
            await state.getVersion(
                'turn-1',
                'Tercera respuesta.',
                async () => {
                    throw new Error(
                        'backend should not be queried again',
                    );
                },
            );

        assert.equal(
            nextVersion,
            2,
        );
    },

);


test(
    'reset forgets previous turn state and reloads persisted state',
    async () => {
        const state =
            new TurnState();

        const externalTurnId =
            'turn-reset-regression';

        const firstVersion =
            await state.getVersion(
                externalTurnId,
                'Primera narrativa.',
                async () => missingTurn(),
            );

        assert.equal(
            firstVersion,
            1,
        );

        const secondVersion =
            await state.getVersion(
                externalTurnId,
                'Segunda narrativa.',
                async () => {
                    throw new Error(
                        'backend should not be queried before reset',
                    );
                },
            );

        assert.equal(
            secondVersion,
            2,
        );

        assert.equal(
            state.tryMarkProcessing(
                externalTurnId,
                secondVersion,
            ),
            true,
        );

        let persistedStateQueries = 0;

        state.reset();

        const versionAfterReset =
            await state.getVersion(
                externalTurnId,
                'Tercera narrativa.',
                async (requestedTurnId) => {
                    persistedStateQueries += 1;

                    assert.equal(
                        requestedTurnId,
                        externalTurnId,
                    );

                    return {
                        exists: true,
                        active_version: 1,
                        narrative: 'Primera narrativa.',
                    };
                },
            );

        assert.equal(
            persistedStateQueries,
            1,
        );

        assert.equal(
            versionAfterReset,
            2,
        );

        assert.equal(
            state.tryMarkProcessing(
                externalTurnId,
                versionAfterReset,
            ),
            true,
        );
    },
);
