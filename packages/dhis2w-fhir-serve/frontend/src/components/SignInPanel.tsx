import { useState, type FormEvent } from 'react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
    basicAuthorization,
    bearerAuthorization,
    signIn,
    signInHeading,
    REFUSED_NOTICE,
    SIGN_IN_LABEL,
    SIGN_IN_NOTES,
    type AuthPosture,
} from '@/lib/auth'

/**
 * What this server asks for before it answers, drawn per posture.
 *
 * ONE FIELD OR TWO, and nothing else on the screen. The panel takes the place of the page rather
 * than floating over it: the app has not read anything yet, so there is nothing behind it to see,
 * and a dialog over an empty frame would only be a dialog over an empty frame.
 *
 * NOTHING IS SENT FROM HERE. Submitting stores the credential this tab will sign its requests with;
 * whether the server accepts it is answered by the next request, and a 401 brings this panel back
 * with `refused` set. That is one round trip rather than two, and it means there is no separate
 * "check my credentials" endpoint for this UI to depend on.
 *
 * THE JWT POSTURE DRAWS THE TOKEN FIELD AND NAMES THE ISSUER. It is a paste field rather than a sign-in
 * form because this server has nowhere to send a username and a password: the token comes from an
 * identity provider it does not run, and the panel says so rather than implying it could get one.
 * The identity is left null for the same reason the deployment-token posture leaves it null - the
 * name on the receipt is the claim the SERVER read out of the token, and a browser reading a name out
 * of the token itself would be a browser asserting who somebody is.
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
    const pastesAToken = posture === 'token' || posture === 'jwt'

    function submit(event: FormEvent<HTMLFormElement>): void {
        event.preventDefault()
        if (pastesAToken) {
            if (token.trim() === '') return
            signIn(bearerAuthorization(token.trim()), null)
            return
        }
        if (username.trim() === '') return
        signIn(basicAuthorization(username.trim(), password), username.trim())
    }

    return (
        <div className="mx-auto w-full max-w-md py-10">
            <Card>
                <CardHeader>
                    <CardTitle>{signInHeading(posture, issuer)}</CardTitle>
                    <CardDescription>{SIGN_IN_NOTES[posture]}</CardDescription>
                </CardHeader>
                <CardContent>
                    {refused && (
                        <p className="text-destructive mb-4 text-sm" role="alert">
                            {REFUSED_NOTICE}
                        </p>
                    )}
                    <form className="grid gap-4" onSubmit={submit}>
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
                        <Button type="submit">{SIGN_IN_LABEL}</Button>
                    </form>
                </CardContent>
            </Card>
        </div>
    )
}
