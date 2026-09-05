import { useState, type FormEvent } from 'react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { checkCredential } from '@/lib/api'
import {
    basicAuthorization,
    bearerAuthorization,
    signIn,
    signInHeading,
    SIGN_IN_LABEL,
    SIGN_IN_NOTES,
    SIGN_IN_REFUSALS,
    SIGN_IN_UNENCODABLE,
    SIGN_IN_UNREACHABLE,
    type AuthPosture,
} from '@/lib/auth'

/**
 * What this server asks for before it answers, drawn per posture.
 *
 * ONE FIELD OR TWO, and nothing else on the screen. The panel takes the place of the page rather
 * than floating over it: the app has not read anything yet, so there is nothing behind it to see,
 * and a dialog over an empty frame would only be a dialog over an empty frame.
 *
 * SUBMITTING ASKS THE SERVER WHO THIS IS, and nothing is kept until it answers. `GET /facade/whoami`
 * carries the authentication check under every scope, so it is the one address that gives a verdict
 * on a credential without doing anything with it. The alternative - storing what was typed and
 * finding out at the next request - is unbearable under the default `write` scope, where every read
 * is open and the first thing that would refuse a wrong password is a submission somebody spent
 * minutes filling in. A wrong password is refused here, at the prompt, in one round trip.
 *
 * A REFUSAL AND AN UNREACHABLE SERVER ARE DIFFERENT SENTENCES. One means retype the password; the
 * other means it was never looked at. Telling a person the wrong one of those is how an afternoon
 * goes into a credential that was right all along.
 *
 * THE NAME THAT IS KEPT IS THE SERVER'S, not what was typed into the box. Under the DHIS2 posture
 * the instance's own spelling of the username is what lands on every receipt, and under the JWT
 * posture the name is a claim this browser never reads for itself - the server read it, and the
 * server said it. The token posture names nobody, because a deployment token is not a person.
 *
 * THE JWT POSTURE DRAWS THE TOKEN FIELD AND NAMES THE ISSUER. It is a paste field rather than a sign-in
 * form because this server has nowhere to send a username and a password: the token comes from an
 * identity provider it does not run, and the panel says so rather than implying it could get one.
 */
export function SignInPanel({
    posture,
    issuer,
    refused,
}: {
    posture: Exclude<AuthPosture, 'none'>
    issuer: string | null
    refused: boolean
}) {
    const [token, setToken] = useState('')
    const [username, setUsername] = useState('')
    const [password, setPassword] = useState('')
    const [checking, setChecking] = useState(false)
    // The panel's own verdict on what was last submitted here. Null until something is submitted,
    // and it takes the place of `refused` - which is the same fact about a credential met elsewhere.
    const [notice, setNotice] = useState<string | null>(null)
    const pastesAToken = posture === 'token' || posture === 'jwt'
    const shown = notice ?? (refused ? SIGN_IN_REFUSALS[posture] : null)

    async function submit(event: FormEvent<HTMLFormElement>): Promise<void> {
        event.preventDefault()
        if (checking) return
        const typed = pastesAToken ? token.trim() : username.trim()
        if (typed === '') return
        // Building the header is the one step here that can fail before anything is sent. Any text a
        // person can type encodes, so this catch is what a browser missing the encoder reads as, and
        // it says so rather than letting the panel sit on a rejected promise with nothing on screen.
        let authorization: string
        try {
            authorization = pastesAToken ? bearerAuthorization(typed) : basicAuthorization(typed, password)
        } catch {
            setNotice(SIGN_IN_UNENCODABLE)
            return
        }
        setChecking(true)
        setNotice(null)
        const checked = await checkCredential(authorization)
        setChecking(false)
        if (checked.outcome === 'refused') {
            setNotice(SIGN_IN_REFUSALS[posture])
            return
        }
        if (checked.outcome === 'unreachable') {
            setNotice(SIGN_IN_UNREACHABLE)
            return
        }
        signIn(authorization, checked.username)
    }

    return (
        <div className="mx-auto w-full max-w-md py-10">
            <Card>
                <CardHeader>
                    <CardTitle>{signInHeading(posture, issuer)}</CardTitle>
                    <CardDescription>{SIGN_IN_NOTES[posture]}</CardDescription>
                </CardHeader>
                <CardContent>
                    {shown !== null && (
                        <p className="text-destructive mb-4 text-sm" role="alert">
                            {shown}
                        </p>
                    )}
                    <form className="grid gap-4" onSubmit={(event) => void submit(event)}>
                        {pastesAToken ? (
                            <div className="grid gap-2">
                                <Label htmlFor="serve-token">Token</Label>
                                <Input
                                    id="serve-token"
                                    type="password"
                                    autoComplete="off"
                                    value={token}
                                    onChange={(event) => setToken(event.target.value)}
                                />
                            </div>
                        ) : (
                            <>
                                <div className="grid gap-2">
                                    <Label htmlFor="dhis2-username">DHIS2 username</Label>
                                    <Input
                                        id="dhis2-username"
                                        autoComplete="username"
                                        value={username}
                                        onChange={(event) => setUsername(event.target.value)}
                                    />
                                </div>
                                <div className="grid gap-2">
                                    <Label htmlFor="dhis2-password">DHIS2 password</Label>
                                    <Input
                                        id="dhis2-password"
                                        type="password"
                                        autoComplete="current-password"
                                        value={password}
                                        onChange={(event) => setPassword(event.target.value)}
                                    />
                                </div>
                            </>
                        )}
                        {/* Disabled rather than relabelled while the check is out: the button says
                            what it does, and one round trip is not long enough to need a second
                            word for it. */}
                        <Button type="submit" disabled={checking} aria-busy={checking}>
                            {SIGN_IN_LABEL}
                        </Button>
                    </form>
                </CardContent>
            </Card>
        </div>
    )
}
